"""ComfyUI Telegram control bot (daemon version).

Started as a background thread by __init__.py when ComfyUI loads.
A supervisor thread restarts the polling loop if it ever dies.

Features:
  - /generate <prompt>: queue the exported workflow with a new prompt
  - workflow parameter overrides from Telegram (/set, /unset, /params, ...)
    persisted to overrides.json and applied on every queued generation
  - per-chat language selection (/lang, ru/en), persisted in chat_settings.json;
    the Telegram command menu is localized per chat as well
  - command menu registered via setMyCommands (visible "/" autocomplete)
  - multi-image delivery via sendMediaGroup albums with retries and backoff
  - server control: /status, /queue, /stop, /clearqueue, /last, /regen
  - user management by admins: /users, /adduser, /deluser
"""

import copy
import json
import logging
import math
import os
import random
import re
import threading
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from typing import NamedTuple

import requests

try:
    from .bot_strings import DEFAULT_LANGUAGE, LANGUAGES, MENU, STRINGS
except ImportError:  # direct import (tests)
    from bot_strings import DEFAULT_LANGUAGE, LANGUAGES, MENU, STRINGS

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WORKFLOW_PATH = os.path.join(BASE_DIR, "workflow_api.json")
OVERRIDES_PATH = os.path.join(BASE_DIR, "overrides.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
CHAT_SETTINGS_PATH = os.path.join(BASE_DIR, "chat_settings.json")
LOG_PATH = os.path.join(BASE_DIR, "bot.log")

DEFAULT_CONFIG = {
    "telegram_token": "",
    "allowed_users": [],
    "admins": [],
    "comfy_host": "127.0.0.1:8188",
    "workflows": {
        "txt2img": "workflow_api.json",
        "img2img": "workflow_img2img_api.json",
    },
    "default_workflow": "txt2img",
    "workflow_file": "workflow_api.json",  # legacy single-workflow option, still honored
    "default_language": DEFAULT_LANGUAGE,
    "generation_timeout": 1800,
    "progress_edit_interval": 5,
}

SEED_PARAMS = ("seed", "noise_seed")
SEED_MAX = 0xFFFFFFFFFFFFFFFF
ADMIN_COMMANDS = {"users", "adduser", "deluser"}
VIDEO_EXTS = {"mp4", "m4v", "mov", "webm", "mkv", "avi"}
_config_lock = threading.Lock()

log = logging.getLogger("controlbot")


def setup_logging():
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        fh = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)


class MsgError(NamedTuple):
    """A localizable error: template key in STRINGS plus format kwargs."""
    key: str
    kw: dict = {}


# --------------------------------------------------------------------------- #
# Config / small stores
# --------------------------------------------------------------------------- #

def load_config():
    """Return a merged config dict, or None when the token is not set yet."""
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        log.info("Created empty config.json — fill in telegram_token and restart ComfyUI.")
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        log.error("config.json is not valid JSON: %s", e)
        return None
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in config.items() if v is not None})
    if not merged.get("telegram_token") or "YOUR" in str(merged.get("telegram_token")):
        return None
    return merged


class JsonStore:
    """Tiny JSON file store tolerant to concurrent access and corruption."""

    def __init__(self, path, default):
        self.path = path
        self.default = default
        self.lock = threading.Lock()

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return copy.deepcopy(self.default)
        if not isinstance(data, dict):
            return copy.deepcopy(self.default)
        merged = copy.deepcopy(self.default)
        merged.update(data)
        return merged

    def load(self):
        with self.lock:
            return self._read()

    def _write(self, data):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            log.error("Failed to save %s: %s", self.path, e)

    def save(self, data):
        with self.lock:
            self._write(data)

    def mutate(self, fn):
        """Atomic read-modify-write (commands run in parallel threads)."""
        with self.lock:
            data = self._read()
            result = fn(data)
            self._write(data)
            return result


# --------------------------------------------------------------------------- #
# Telegram API
# --------------------------------------------------------------------------- #

class TelegramAPI:
    def __init__(self, token):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()

    def _request(self, method, data=None, files=None, timeout=(10, 60)):
        """POST with 429 backoff. Returns the result payload or None."""
        for _ in range(4):
            try:
                r = self.session.post(
                    f"{self.base}/{method}", data=data, files=files, timeout=timeout
                )
            except requests.RequestException as e:
                log.warning("Telegram %s network error: %s", method, e)
                time.sleep(2)
                continue
            if r.status_code == 429:
                try:
                    wait = r.json().get("parameters", {}).get("retry_after", 3) + 1
                except Exception:
                    wait = 4
                log.warning("Telegram %s rate limited, waiting %ss", method, wait)
                time.sleep(wait)
                continue
            try:
                payload = r.json()
            except Exception:
                log.warning("Telegram %s returned non-JSON (%s)", method, r.status_code)
                return None
            if not payload.get("ok"):
                log.warning("Telegram %s failed: %s", method, payload.get("description"))
                return None
            return payload.get("result")
        return None

    def get(self, method, params=None, timeout=(10, 40)):
        try:
            r = self.session.get(f"{self.base}/{method}", params=params, timeout=timeout)
            payload = r.json()
        except Exception as e:
            raise ConnectionError(f"getUpdates failed: {e}") from e
        if not payload.get("ok"):
            raise ConnectionError(f"{method} failed: {payload.get('description')}")
        return payload.get("result")

    def send_message(self, chat_id, text, parse_mode=None):
        data = {"chat_id": chat_id, "text": text[:4096]}
        if parse_mode:
            data["parse_mode"] = parse_mode
        result = self._request("sendMessage", data=data)
        if result:
            return result.get("message_id")
        return None

    def edit_message(self, chat_id, message_id, text):
        return self._request(
            "editMessageText",
            data={"chat_id": chat_id, "message_id": message_id, "text": text[:4096]},
        )

    def send_photo(self, chat_id, image_bytes, caption="", reply_markup=None):
        files = {"photo": ("image.png", image_bytes, "image/png")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self._request("sendPhoto", data=data, files=files, timeout=(10, 120))

    def send_video(self, chat_id, video_bytes, caption="", filename="video.mp4"):
        ext = os.path.splitext(filename)[1].lower()
        mime = "video/webm" if ext == ".webm" else "video/mp4"
        files = {"video": (filename, video_bytes, mime)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]
        return self._request("sendVideo", data=data, files=files, timeout=(10, 300))

    def send_album(self, chat_id, images, caption=""):
        """Send 2..10 photos as one album. Returns True on success."""
        media, files = [], {}
        for i, blob in enumerate(images):
            key = f"img{i}"
            files[key] = ("image.png", blob, "image/png")
            item = {"type": "photo", "media": f"attach://{key}"}
            if i == 0 and caption:
                item["caption"] = caption[:1024]
            media.append(item)
        result = self._request(
            "sendMediaGroup",
            data={"chat_id": chat_id, "media": json.dumps(media)},
            files=files,
            timeout=(10, 180),
        )
        return result is not None

    def download_file(self, file_id):
        """Download a Telegram file by id. Returns (bytes_or_None, MsgError_or_None)."""
        info = self._request("getFile", data={"file_id": file_id})
        if not info or not info.get("file_path"):
            log.warning("getFile failed for %s: %s", file_id, info)
            return None, MsgError("img_dl_failed", {"reason": "getFile"})
        if info.get("file_size") and info["file_size"] > 20_000_000:
            log.warning("Telegram file too large: %s bytes", info["file_size"])
            return None, MsgError("img_too_large")
        path = info["file_path"]
        status = None
        for attempt in range(1, 4):
            try:
                # documented format: https://api.telegram.org/file/bot<token>/<file_path>
                r = self.session.get(
                    f"https://api.telegram.org/file/bot{self.token}/{path}", timeout=(10, 120)
                )
            except requests.RequestException as e:
                log.warning("Telegram file download attempt %s failed: %s", attempt, e)
                time.sleep(2)
                continue
            status = r.status_code
            if status == 200:
                return r.content, None
            log.warning(
                "Telegram file download attempt %s: HTTP %s %s", attempt, status, r.text[:200]
            )
            if status == 429:
                try:
                    wait = r.json().get("parameters", {}).get("retry_after", 3) + 1
                except Exception:
                    wait = 4
                time.sleep(wait)
            else:
                time.sleep(2)
        return None, MsgError("img_dl_failed", {"reason": f"HTTP {status}" if status else "network"})


# --------------------------------------------------------------------------- #
# ComfyUI API helpers
# --------------------------------------------------------------------------- #

class ComfyAPI:
    def __init__(self, host):
        self.host = host
        self.session = requests.Session()
        self._object_info = {}

    def get(self, path, timeout=10):
        try:
            r = self.session.get(f"http://{self.host}{path}", timeout=timeout)
            return r.json()
        except Exception as e:
            log.warning("ComfyUI GET %s failed: %s", path, e)
            return None

    def post(self, path, payload=None, timeout=15):
        try:
            r = self.session.post(f"http://{self.host}{path}", json=payload, timeout=timeout)
            if r.status_code >= 400:
                try:
                    return {"__http_error__": r.status_code, **r.json()}
                except Exception:
                    return {"__http_error__": r.status_code}
            if not r.content.strip():
                return {}  # some endpoints reply 200 with an empty body (e.g. /interrupt)
            return r.json()
        except Exception as e:
            log.warning("ComfyUI POST %s failed: %s", path, e)
            return None

    def fetch_image(self, filename, subfolder, folder_type):
        try:
            r = self.session.get(
                f"http://{self.host}/view",
                params={"filename": filename, "subfolder": subfolder, "type": folder_type},
                timeout=60,
            )
            if r.status_code == 200:
                return r.content
        except Exception as e:
            log.warning("Fetching image %s failed: %s", filename, e)
        return None

    def upload_image(self, blob, filename):
        """Upload an image into ComfyUI's input folder. Returns the stored name or None."""
        try:
            r = self.session.post(
                f"http://{self.host}/upload/image",
                files={"image": (filename, blob, "application/octet-stream")},
                data={"overwrite": "true"},
                timeout=(10, 120),
            )
            if r.status_code == 200:
                return (r.json() or {}).get("name")
        except Exception as e:
            log.warning("Image upload failed: %s", e)
        return None

    def object_info(self, class_type, refresh=False):
        """Node schema from /object_info/<class>. Cached unless refresh=True —
        folder-listing nodes (LoadImage/LoraLoader/...) change on disk, callers
        that validate file names must refresh."""
        if refresh or class_type not in self._object_info:
            info = self.get(f"/object_info/{class_type}", timeout=30)
            self._object_info[class_type] = (info or {}).get(class_type) or {}
        return self._object_info[class_type]


# --------------------------------------------------------------------------- #
# Workflow helpers
# --------------------------------------------------------------------------- #

def is_wire(value):
    """ComfyUI API format: connections look like ["<node_id>", <output_index>]."""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )


def node_title(node):
    return (node.get("_meta") or {}).get("title", "")


def scalar_inputs(node):
    return {
        k: v
        for k, v in node.get("inputs", {}).items()
        if not is_wire(v)
    }


def find_load_image_node(workflow):
    """The node that takes an input image (img2img workflows), or None."""
    for nid, node in workflow.items():
        if node.get("class_type") in ("LoadImage", "LoadImageOutput") and "image" in node.get("inputs", {}):
            return nid
    return None


def find_positive_prompt_node(workflow):
    """Trace the KSampler's positive wire backward to the first node with a text input."""
    for node in workflow.values():
        if node.get("class_type") in (
            "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
        ):
            positive = node.get("inputs", {}).get("positive")
            if isinstance(positive, list) and str(positive[0]) in workflow:
                queue, seen = [str(positive[0])], set()
                while queue:
                    nid = queue.pop(0)
                    if nid in seen or nid not in workflow:
                        continue
                    seen.add(nid)
                    text = workflow[nid].get("inputs", {}).get("text")
                    if isinstance(text, str):
                        return nid
                    for v in workflow[nid].get("inputs", {}).values():
                        if is_wire(v) and str(v[0]) in workflow:
                            queue.append(str(v[0]))

    for node_id, node in workflow.items():
        if node.get("class_type") == "CLIPTextEncode" and isinstance(
            node.get("inputs", {}).get("text"), str
        ):
            return str(node_id)
    return None


def resolve_target(workflow, key):
    """Resolve a node by id, exact title, class_type or unique substring.

    Returns (node_id, None) or (None, MsgError).
    """
    k = key.strip().lower()
    if k in workflow:
        return k, None
    for nid, node in workflow.items():
        if node_title(node).lower() == k:
            return nid, None

    def match(nid, node):
        hay = f"{nid} {node.get('class_type', '')} {node_title(node)}".lower()
        return k in hay

    matches = [nid for nid, node in workflow.items() if match(nid, node)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        listing = "\n".join(
            f"  • «{nid}» {workflow[nid].get('class_type')} — «{node_title(workflow[nid])}»"
            for nid in matches[:8]
        )
        return None, MsgError("node_ambiguous", {"key": key, "list": listing})
    return None, MsgError("node_not_found", {"key": key})


def collect_history_images(history_entry):
    """All output images of one history entry, deduplicated, outputs before previews."""
    seen, out = set(), []
    for node_output in (history_entry or {}).get("outputs", {}).values():
        for img in node_output.get("images", []):
            try:
                key = (img["filename"], img["subfolder"], img["type"])
            except KeyError:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(img)
    out.sort(key=lambda i: 0 if i.get("type") == "output" else 1)
    return out


def parse_value(raw):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        return raw


def describe_value(v):
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."


def chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def nearest_4n1(frames):
    """Closest valid Wan latent length: 4n+1 (min 5)."""
    n = max(1, int(round((int(frames) - 1) / 4)))
    return 4 * n + 1


def plan_video_segments(total_frames, cap=81):
    """Split a frame budget into Wan segments of <= cap frames (each 4n+1)."""
    if total_frames <= cap:
        return [nearest_4n1(total_frames)]
    cycles = -(-total_frames // cap)
    last = total_frames - (cycles - 1) * cap
    return [cap] * (cycles - 1) + [nearest_4n1(max(last, 5))]


def video_last_frame_png(mp4_bytes):
    """Decode the last frame of an mp4 (bytes) -> PNG bytes, or None."""
    import av
    import io
    container = av.open(io.BytesIO(mp4_bytes))
    last = None
    for frame in container.decode(video=0):
        last = frame
    container.close()
    if last is None:
        return None
    out = io.BytesIO()
    last.to_image().save(out, format="PNG")
    return out.getvalue()


def assemble_mp4(mp4_blobs, fps=24):
    """Concatenate segment mp4s: drop the first frame of segments 2+, re-encode h264."""
    import av
    import io
    frames = []
    for i, blob in enumerate(mp4_blobs):
        container = av.open(io.BytesIO(blob))
        first = True
        for frame in container.decode(video=0):
            if i > 0 and first:
                first = False
                continue
            frames.append(frame)
        container.close()
    if not frames:
        return None
    buf = io.BytesIO()
    out = av.open(buf, "w", format="mp4")
    stream = out.add_stream("h264", rate=fps)
    stream.width = frames[0].width
    stream.height = frames[0].height
    stream.pix_fmt = "yuv420p"
    stream.options = {"crf": "23"}
    for frame in frames:
        for packet in stream.encode(frame):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    return buf.getvalue()


def format_uptime(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if days:
        return f"{days}d {h:02}:{m:02}:{s:02}"
    return f"{h:02}:{m:02}:{s:02}"


# Live self-monitoring state, shared by the polling loop, the supervisor and the watchdog.
_bot_state = {
    "started_at": time.time(),
    "restarts": 0,      # polling loop crash-restarts by the supervisor
    "heartbeat": 0.0,   # last time the polling loop iterated
    "updates": 0,       # Telegram updates received
}
_state_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# The bot
# --------------------------------------------------------------------------- #

class ControlBot:
    def __init__(self, config):
        self.config = config
        self.api = TelegramAPI(config["telegram_token"])
        self.comfy = ComfyAPI(config["comfy_host"])
        self.overrides = JsonStore(OVERRIDES_PATH, {"prompt": None, "nodes": {}})
        self.state = JsonStore(STATE_PATH, {"last": None})
        self.chat_settings = JsonStore(CHAT_SETTINGS_PATH, {"chats": {}})
        self.allowed_users = set(config.get("allowed_users") or [])
        self.admins = set(config.get("admins") or [])
        self._lang_cache = {}
        self._menu_registered = False
        self._chat_menus_registered = False
        self._pending_masks = {}

    # ------------------------------------------------------------------ #
    # Localization
    # ------------------------------------------------------------------ #

    @property
    def default_lang(self):
        dl = self.config.get("default_language", DEFAULT_LANGUAGE)
        return dl if dl in LANGUAGES else DEFAULT_LANGUAGE

    def get_lang(self, chat_id):
        """Language of a chat: explicit /lang setting, else the default."""
        key = str(chat_id)
        lang = self._lang_cache.get(key)
        if lang is None:
            lang = (self.chat_settings.load().get("chats") or {}).get(key)
            if lang not in LANGUAGES:
                lang = self.default_lang
            self._lang_cache[key] = lang
        return lang

    def ensure_chat_lang(self, chat_id, language_code, chat_type="private"):
        """Auto-detect the language from the client's language_code on first contact.

        Private chats only: in groups the language belongs to the chat and is
        set by an admin via /lang, not by whoever happens to write first.
        """
        if chat_type != "private":
            return
        key = str(chat_id)
        if key in self._lang_cache:
            return
        stored = (self.chat_settings.load().get("chats") or {}).get(key)
        if stored in LANGUAGES:
            self._lang_cache[key] = stored
            return
        pref = (language_code or "").split("-")[0].lower()
        if pref in LANGUAGES and pref != self.default_lang:
            self.chat_settings.mutate(lambda s: s.setdefault("chats", {}).update({key: pref}))
            self._lang_cache[key] = pref
            log.info("Language for chat %s auto-detected: %s", chat_id, pref)

    def set_chat_lang(self, chat_id, lang):
        key = str(chat_id)
        self.chat_settings.mutate(lambda s: s.setdefault("chats", {}).update({key: lang}))
        self._lang_cache[key] = lang
        if lang == self.default_lang:
            # no need for a per-chat menu — drop it so the default one applies
            self.api._request(
                "deleteMyCommands",
                data={"scope": json.dumps({"type": "chat", "chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id})},
            )
        else:
            self.set_chat_menu(chat_id, lang)

    def t(self, chat_id, skey, /, **kw):
        """Translate a template for the chat's language.

        chat_id and skey are positional-only so template placeholders may be
        named `chat_id` or `key` without colliding.
        """
        lang = self.get_lang(chat_id)
        text = STRINGS.get(lang, {}).get(skey) or STRINGS[DEFAULT_LANGUAGE].get(skey) or skey
        if not kw:
            return text
        try:
            return text.format(**kw)
        except Exception as e:
            log.warning("String format failed (%s/%s): %s", lang, skey, e)
            return text

    def send_err(self, chat_id, err):
        self.api.send_message(chat_id, self.t(chat_id, err.key, **err.kw))

    # ------------------------------------------------------------------ #
    # Config / admins
    # ------------------------------------------------------------------ #

    def is_admin(self, user_id):
        return user_id in self.admins

    def mutate_overrides(self, fn):
        return self.overrides.mutate(fn)

    def update_config(self, mutator):
        """Atomically modify config.json on disk, then refresh in-memory state."""
        with _config_lock:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            mutator(cfg)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            os.replace(tmp, CONFIG_PATH)
        fresh = load_config()
        if fresh:
            self.config = fresh
            self.allowed_users = set(fresh.get("allowed_users") or [])
            self.admins = set(fresh.get("admins") or [])

    # ------------------------------------------------------------------ #
    # Telegram plumbing
    # ------------------------------------------------------------------ #

    def menu_commands(self, lang):
        return [
            {"command": cmd, "description": desc.get(lang) or desc[DEFAULT_LANGUAGE]}
            for cmd, desc in MENU
        ]

    def set_chat_menu(self, chat_id, lang):
        """Register the localized command menu for one chat (overrides the default)."""
        scope = {"type": "chat", "chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id}
        result = self.api._request(
            "setMyCommands",
            data={
                "commands": json.dumps(self.menu_commands(lang)),
                "scope": json.dumps(scope),
            },
        )
        return result is not None

    def register_commands(self):
        result = self.api._request(
            "setMyCommands", data={"commands": json.dumps(self.menu_commands(self.default_lang))}
        )
        self._menu_registered = result is not None
        log.info("Command menu registered: %s", self._menu_registered)
        self.register_chat_menus()
        return self._menu_registered

    def register_chat_menus(self):
        """Re-apply per-chat localized menus (after boot or /lang changes elsewhere)."""
        chats = (self.chat_settings.load().get("chats") or {})
        ok = True
        for chat_id, lang in chats.items():
            if lang not in LANGUAGES:
                continue
            try:
                if lang == self.default_lang:
                    continue  # default menu already covers this chat
                ok = self.set_chat_menu(chat_id, lang) and ok
            except Exception:
                ok = False
        self._chat_menus_registered = ok
        return ok

    def run_polling(self):
        """Long-poll loop. Returns only when the config file changed the token."""
        offset = 0
        try:
            self.api.get("deleteWebhook", params={"drop_pending_updates": "false"}, timeout=(10, 15))
        except Exception:
            pass
        log.info(
            "[Telegram Bot] Online. Allowed users: %s, workflow: %s",
            sorted(self.allowed_users), self.config.get("workflow_file"),
        )
        try:
            config_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            config_mtime = None
        failures = 0
        last_menu_try = 0.0
        while True:
            try:
                with _state_lock:
                    _bot_state["heartbeat"] = time.time()
                if time.time() - last_menu_try > 60:
                    last_menu_try = time.time()
                    if not self._menu_registered:
                        self.register_commands()
                    elif not self._chat_menus_registered:
                        self.register_chat_menus()
                try:
                    mtime_now = os.path.getmtime(CONFIG_PATH)
                except OSError:
                    mtime_now = None
                if mtime_now != config_mtime and mtime_now is not None:
                    config_mtime = mtime_now
                    fresh = load_config()
                    if fresh and fresh["telegram_token"] != self.config["telegram_token"]:
                        log.info("Token changed in config.json — restarting daemon.")
                        return
                    if fresh:
                        self.config = fresh
                        self.allowed_users = set(fresh.get("allowed_users") or [])
                        self.admins = set(fresh.get("admins") or [])
                        self._lang_cache.clear()
                        log.info("config.json reloaded (allowed users: %s)", sorted(self.allowed_users))

                updates = self.api.get(
                    "getUpdates",
                    params={
                        "timeout": 30,
                        "offset": offset or None,
                        "allowed_updates": json.dumps(["message", "callback_query"]),
                    },
                )
                failures = 0
                with _state_lock:
                    _bot_state["updates"] += len(updates or [])
                for upd in updates or []:
                    offset = max(offset, upd["update_id"] + 1)
                    cb = upd.get("callback_query")
                    if cb:
                        threading.Thread(
                            target=self.handle_callback, args=(cb,), daemon=True
                        ).start()
                        continue
                    msg = upd.get("message")
                    if not msg:
                        continue
                    # a photo with a "/generate ..." caption works like a text command;
                    # an image attached or replied to feeds img2img workflows
                    text = msg.get("text") or msg.get("caption")
                    if not text:
                        continue
                    chat_id = msg["chat"]["id"]
                    chat_type = msg["chat"].get("type", "private")
                    user_id = (msg.get("from") or {}).get("id")
                    if user_id not in self.allowed_users and user_id not in self.admins:
                        log.warning("Denied user %s (chat %s, type %s)", user_id, chat_id, chat_type)
                        if chat_type == "private":
                            self.api.send_message(
                                chat_id,
                                self.t(chat_id, "deny_private", user_id=user_id),
                            )
                        continue
                    self.ensure_chat_lang(
                        chat_id, (msg.get("from") or {}).get("language_code"), chat_type
                    )
                    reply_user_id = None
                    replied = msg.get("reply_to_message") or {}
                    if isinstance(replied.get("from"), dict):
                        reply_user_id = replied["from"].get("id")
                    image_ref = self.find_image_ref(msg)
                    threading.Thread(
                        target=self.handle_text,
                        args=(chat_id, text, chat_type, user_id, reply_user_id, image_ref),
                        daemon=True,
                    ).start()
            except ConnectionError as e:
                failures += 1
                log.warning("Polling error (%s), retry in %ss", e, min(5 * failures, 60))
                time.sleep(min(5 * failures, 60))
            except Exception:
                log.error("Polling loop crashed:\n%s", traceback.format_exc())
                raise

    def handle_text(self, chat_id, text, chat_type="private", user_id=None, reply_user_id=None, image_ref=None):
        try:
            m = re.match(r"^/([a-zA-Z_]+)(@\S+)?\s*([\s\S]*)$", text.strip())
            if not m:
                if chat_type == "private":
                    self.api.send_message(chat_id, self.t(chat_id, "not_a_command"))
                return
            cmd, arg = m.group(1).lower(), (m.group(3) or "").strip()
            if cmd == "id":  # available to everyone, so people can report their ID
                self.cmd_id(chat_id, user_id)
                return
            if user_id not in self.allowed_users and not self.is_admin(user_id):
                log.warning("Denied user %s (command /%s)", user_id, cmd)
                if chat_type == "private":
                    self.api.send_message(chat_id, self.t(chat_id, "deny_private_short"))
                return
            if cmd in ADMIN_COMMANDS and not self.is_admin(user_id):
                self.api.send_message(chat_id, self.t(chat_id, "admin_only"))
                return
            handler = getattr(self, f"cmd_{cmd}", None)
            if handler is None:
                if chat_type == "private":
                    self.api.send_message(
                        chat_id, self.t(chat_id, "unknown_command", cmd=cmd)
                    )
                return
            if cmd in ("adduser", "deluser"):
                handler(chat_id, arg, reply_user_id)
            elif cmd == "lang":
                handler(chat_id, arg, chat_type, user_id)
            elif cmd == "generate":
                handler(chat_id, arg, image_ref)
            elif cmd == "cnet":
                handler(chat_id, arg, chat_type, user_id, image_ref)
            elif cmd == "lora":
                handler(chat_id, arg, chat_type, user_id)
            elif cmd == "vseconds":
                handler(chat_id, arg, chat_type, user_id)
            else:
                handler(chat_id, arg)
        except Exception:
            log.error("Command failed:\n%s", traceback.format_exc())
            self.api.send_message(chat_id, self.t(chat_id, "internal_error"))

    # ------------------------------------------------------------------ #
    # Workflow access
    # ------------------------------------------------------------------ #

    def load_workflow(self, name=None):
        workflows = self.available_workflows()
        name = name or self.get_chat_workflow(None)
        path = os.path.join(BASE_DIR, workflows[name])
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ----- workflow selection (per chat, persisted) ---------------------- #

    def available_workflows(self):
        merged = dict(DEFAULT_CONFIG["workflows"])
        merged.update(self.config.get("workflows") or {})
        return {k: v for k, v in merged.items() if isinstance(v, str)}

    def get_chat_workflow(self, chat_id=None):
        """Active workflow name for a chat; falls back to the config default."""
        stored = None
        if chat_id is not None:
            stored = (self.chat_settings.load().get("workflows") or {}).get(str(chat_id))
        if stored in self.available_workflows():
            return stored
        default = self.config.get("default_workflow", "txt2img")
        return default if default in self.available_workflows() else next(iter(self.available_workflows()))

    def set_chat_workflow(self, chat_id, name):
        self.chat_settings.mutate(
            lambda s: s.setdefault("workflows", {}).update({str(chat_id): name})
        )

    @staticmethod
    def extract_image_ref(msg):
        """Image attached to a message: Telegram photo (largest size) or image document."""
        if not isinstance(msg, dict):
            return None
        photos = msg.get("photo")
        if photos:
            best = max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))
            return {"file_id": best["file_id"], "ext": "jpg"}
        doc = msg.get("document") or {}
        if (doc.get("mime_type") or "").startswith("image/"):
            name = doc.get("file_name") or "image"
            ext = os.path.splitext(name)[1].lstrip(".") or "png"
            return {"file_id": doc["file_id"], "ext": ext}
        return None

    @staticmethod
    def is_video_workflow(workflow):
        return any(
            "Video" in n.get("class_type", "")
            for n in workflow.values()
        )

    def find_image_ref(self, msg):
        """Image from the message itself, or from the message it replies to."""
        return self.extract_image_ref(msg) or self.extract_image_ref(msg.get("reply_to_message"))

    # ----- ControlNet (Z-Image Fun Union model patch) --------------------- #

    def get_cnet_settings(self, chat_id):
        defaults = {"enabled": False, "strength": 0.8, "prep": "", "patch": "", "file_id": None, "ext": "png"}
        stored = (self.chat_settings.load().get("cnet") or {}).get(str(chat_id)) or {}
        out = dict(defaults)
        out.update({k: v for k, v in stored.items() if v is not None})
        return out

    def set_cnet_settings(self, chat_id, **kw):
        self.chat_settings.mutate(
            lambda s: s.setdefault("cnet", {}).setdefault(str(chat_id), {}).update(kw)
        )

    def available_patches(self):
        info = self.comfy.object_info("ModelPatchLoader", refresh=True)
        spec = ((info.get("input") or {}).get("required") or {}).get("name")
        return spec[0] if spec and isinstance(spec[0], list) else []

    def available_preprocessors(self):
        info = self.comfy.object_info("AIO_Preprocessor", refresh=True)
        inputs = info.get("input") or {}
        # newer pack versions moved the combo from required to optional
        spec = (inputs.get("required") or {}).get("preprocessor") or (inputs.get("optional") or {}).get("preprocessor")
        return spec[0] if spec and isinstance(spec[0], list) else []

    def pick_patch_name(self, settings):
        """The model patch to load: explicit choice, else the full Union-2.1."""
        patches = self.available_patches()
        if not patches:
            return None, MsgError("cnet_patch_missing")
        want = settings.get("patch")
        if want and want in patches:
            return want, None
        for p in patches:
            if "Union-2.1" in p and "8steps" not in p and "lite" not in p:
                return p, None
        return patches[0], None

    def inject_controlnet(self, workflow, chat_id):
        """Wire an approved ControlNet mask into a workflow (txt2img and img2img).

        Patches the MODEL (DiffSynth-style): <model source> → ZImageFunControlnet → sampler.
        The mask must have been approved via /cnet. Returns (workflow, MsgError_or_None).
        """
        st = self.get_cnet_settings(chat_id)
        if not st.get("enabled"):
            return workflow, None
        mask_name = st.get("mask_name")
        if not mask_name:
            return workflow, MsgError("cnet_need_reference")
        info = self.comfy.object_info("LoadImage", refresh=True)
        combo = ((info.get("input") or {}).get("required") or {}).get("image")
        input_files = combo[0] if combo and isinstance(combo[0], list) else []
        if mask_name not in input_files:
            log.warning("ControlNet mask %s is gone from the input folder", mask_name)
            return workflow, MsgError("cnet_mask_lost")

        sampler_id = next(
            (nid for nid, n in workflow.items() if n.get("class_type") in ("KSampler", "KSamplerAdvanced")),
            None,
        )
        if not sampler_id:
            return workflow, MsgError("cnet_need_img2img")
        old_model = workflow[sampler_id]["inputs"].get("model")
        vae_node = next((n for n in workflow.values() if n.get("class_type") == "VAEEncode"), None)
        old_vae = (vae_node or {}).get("inputs", {}).get("vae")
        if not is_wire(old_vae):
            # txt2img workflows have no VAEEncode — take the VAE from its loader
            vae_loader = next((nid for nid, n in workflow.items() if n.get("class_type") == "VAELoader"), None)
            old_vae = [vae_loader, 0] if vae_loader else None
        if not is_wire(old_model) or not is_wire(old_vae):
            return workflow, MsgError("cnet_need_img2img")
        patch_name, err = self.pick_patch_name(st)
        if err:
            return workflow, err

        workflow["__cnet_patch"] = {
            "inputs": {"name": patch_name},
            "class_type": "ModelPatchLoader",
            "_meta": {"title": "ControlNet"},
        }
        workflow["__cnet_img"] = {
            "inputs": {"image": mask_name},
            "class_type": "LoadImage",
            "_meta": {"title": "ControlNet маска"},
        }
        image_wire = ["__cnet_img", 0]
        prep = st.get("prep")
        if prep:
            preps = self.available_preprocessors()
            if prep not in preps:
                shown = ", ".join(preps[:12]) if preps else "—"
                return workflow, MsgError("cnet_mode_missing", {"name": prep, "list": shown})
            workflow["__cnet_prep"] = {
                "inputs": {"image": image_wire, "preprocessor": prep},
                "class_type": "AIO_Preprocessor",
                "_meta": {"title": "ControlNet препроцессор"},
            }
            image_wire = ["__cnet_prep", 0]
        workflow["__cnet_apply"] = {
            "inputs": {
                "model": old_model,
                "model_patch": ["__cnet_patch", 0],
                "vae": old_vae,
                "strength": float(st.get("strength", 0.8)),
                "image": image_wire,
            },
            "class_type": "ZImageFunControlnet",
            "_meta": {"title": "ControlNet"},
        }
        workflow[sampler_id]["inputs"]["model"] = ["__cnet_apply", 0]
        return workflow, None

    def cmd_cnet(self, chat_id, arg, chat_type="private", user_id=None, image_ref=None):
        if chat_type != "private" and not self.is_admin(user_id):
            self.api.send_message(chat_id, self.t(chat_id, "cnet_group_admin_only"))
            return
        st = self.get_cnet_settings(chat_id)
        parts = arg.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        # a photo with the /cnet caption (or a /cnet reply to a photo) uploads a reference:
        # it is preprocessed into a mask and sent back for approval
        if image_ref and not sub:
            self.api.send_message(chat_id, self.t(chat_id, "cnet_mask_preparing"))
            err = self.prepare_cnet_mask(chat_id, image_ref, st)
            if err:
                self.send_err(chat_id, err)
            return

        if not sub:
            mode = self.t(chat_id, "cnet_mode_none") if not st["prep"] else st["prep"]
            self.api.send_message(chat_id, self.t(
                chat_id, "cnet_status",
                state=self.t(chat_id, "cnet_on" if st["enabled"] else "cnet_off"),
                mode=mode, strength=st["strength"],
                image=self.t(chat_id, "cnet_image_yes" if st.get("mask_name") else "cnet_image_no"),
                name=self.get_chat_workflow(chat_id),
            ))
            return

        if sub in ("on", "off"):
            self.set_cnet_settings(chat_id, enabled=(sub == "on"))
            if sub == "off":
                self.api.send_message(chat_id, self.t(chat_id, "cnet_off"))
                return
            _, err = self.pick_patch_name(st)
            wf_name = self.get_chat_workflow(chat_id)
            self.api.send_message(
                chat_id,
                self.t(chat_id, "cnet_on" if err is None else "cnet_on_no_model", name=wf_name),
            )
            return

        if sub == "strength":
            try:
                value = float(rest.replace(",", "."))
            except ValueError:
                self.api.send_message(chat_id, self.t(chat_id, "cnet_strength_bad"))
                return
            value = max(-10.0, min(10.0, value))
            self.set_cnet_settings(chat_id, strength=value)
            self.api.send_message(chat_id, self.t(chat_id, "cnet_strength_set", value=value))
            return

        if sub in ("mode", "prep"):
            preps = self.available_preprocessors()
            if not rest:
                self.api.send_message(chat_id, self.t(
                    chat_id, "cnet_mode_missing", name=st["prep"] or "—",
                    list=", ".join(preps[:12]) if preps else self.t(chat_id, "cnet_modes_empty"),
                ))
                return
            if rest.lower() in ("off", "none", "нет"):
                self.set_cnet_settings(chat_id, prep="")
                self.api.send_message(chat_id, self.t(chat_id, "cnet_mode_cleared"))
                return
            if rest.lower() in ("list", "список"):
                if not preps:
                    self.api.send_message(chat_id, self.t(chat_id, "cnet_modes_empty"))
                    return
                lines = [f"{i}. {p}" for i, p in enumerate(preps[:40], 1)]
                if len(preps) > 40:
                    lines.append("…")
                self.api.send_message(chat_id, self.t(chat_id, "cnet_mode_list", list="\n".join(lines)))
                return
            aliases = {
                "bones": "openpose", "bone": "openpose", "skeleton": "openpose",
                "pose": "openpose", "depth": "depth", "canny": "canny",
                "hed": "hed", "mlsd": "mlsd", "lineart": "lineart",
                "scribble": "scribble", "gray": "gray",
            }
            target = aliases.get(rest.lower(), rest.lower())
            match = next((p for p in preps if p.lower() == rest.lower()), None)
            if match is None:
                match = next((p for p in preps if target in p.lower()), None)
            if match is None:
                shown = ", ".join(preps[:12]) if preps else self.t(chat_id, "cnet_modes_empty")
                self.api.send_message(chat_id, self.t(chat_id, "cnet_mode_missing", name=rest, list=shown))
                return
            self.set_cnet_settings(chat_id, prep=match)
            self.api.send_message(
                chat_id,
                self.t(chat_id, "cnet_mode_set", name=match)
                + "\n" + self.t(chat_id, "cnet_mask_remake_hint"),
            )
            return

        if sub == "model":
            patches = self.available_patches()
            if rest:
                match = next((p for p in patches if rest.lower() in p.lower()), None)
                if match is None:
                    self.api.send_message(chat_id, self.t(chat_id, "cnet_patch_missing"))
                    return
                self.set_cnet_settings(chat_id, patch=match)
                self.api.send_message(chat_id, self.t(chat_id, "cnet_mode_set", name=match))
                return
            self.api.send_message(chat_id, self.t(chat_id, "cnet_mode_missing", name=st["patch"] or "—", list=", ".join(patches[:8])))
            return

        if sub == "clear":
            self.set_cnet_settings(chat_id, mask_name=None, file_id=None, ext="png")
            self.api.send_message(chat_id, self.t(chat_id, "cnet_image_cleared"))
            return

        self.api.send_message(chat_id, self.t(chat_id, "cnet_unknown", sub=sub))

    def prepare_cnet_mask(self, chat_id, image_ref, settings):
        """Reference photo → preprocessor run in ComfyUI → mask preview for approval."""
        prep = settings.get("prep") or "none"
        preps = self.available_preprocessors()
        if preps and prep != "none" and prep not in preps:
            return MsgError("cnet_mode_missing", {"name": prep, "list": ", ".join(preps[:12])})
        blob, dl_err = self.api.download_file(image_ref["file_id"])
        if not blob:
            return dl_err
        ref_name = self.comfy.upload_image(blob, f"tg_{uuid.uuid4().hex}.{image_ref['ext']}")
        if not ref_name:
            return MsgError("img_upload_fail")
        workflow = {
            "__mask_load": {"inputs": {"image": ref_name}, "class_type": "LoadImage"},
            "__mask_prep": {
                "inputs": {"image": ["__mask_load", 0], "preprocessor": prep, "resolution": 1024},
                "class_type": "AIO_Preprocessor",
            },
            "__mask_save": {
                "inputs": {"filename_prefix": f"cnet_mask_{chat_id}", "images": ["__mask_prep", 0]},
                "class_type": "SaveImage",
            },
        }
        prompt_id, client_id, err = self.queue_workflow(chat_id, workflow)
        if err:
            return MsgError("cnet_mask_failed", {"reason": err})
        started = time.time()
        entry = None
        while time.time() - started < 300:
            time.sleep(2)
            history = self.comfy.get(f"/history/{prompt_id}", timeout=15)
            if history and prompt_id in history:
                entry = history[prompt_id]
                break
        if entry is None:
            return MsgError("cnet_mask_timeout")
        images = collect_history_images(entry)
        if not images:
            return MsgError("cnet_mask_failed", {"reason": "no output"})
        img = images[0]
        blob = self.comfy.fetch_image(img["filename"], img["subfolder"], img["type"])
        if not blob:
            return MsgError("cnet_mask_failed", {"reason": "fetch"})
        keyboard = {"inline_keyboard": [[
            {"text": self.t(chat_id, "cnet_btn_use"), "callback_data": "cnet_ok"},
            {"text": self.t(chat_id, "cnet_btn_cancel"), "callback_data": "cnet_cancel"},
        ]]}
        msg_id = self.api.send_photo(
            chat_id, blob,
            caption=self.t(chat_id, "cnet_mask_ready", mode=prep),
            reply_markup=json.dumps(keyboard),
        )
        self._pending_masks[str(chat_id)] = {
            "images": images,
            "msg_id": msg_id,
            "chat_type": chat_id,
        }
        return None

    def _approve_mask(self, chat_id):
        """Store the pending mask as the active ControlNet image. Returns error MsgError or None."""
        pending = self._pending_masks.pop(str(chat_id), None)
        if not pending:
            return MsgError("cnet_no_pending_msg")
        img = pending["images"][0]
        blob = self.comfy.fetch_image(img["filename"], img["subfolder"], img["type"])
        if not blob:
            return MsgError("cnet_mask_failed", {"reason": "fetch"})
        name = self.comfy.upload_image(blob, f"tg_cnetmask_{uuid.uuid4().hex}.png")
        if not name:
            return MsgError("img_upload_fail")
        self.set_cnet_settings(chat_id, mask_name=name)
        log.info("ControlNet mask approved for chat %s: %s", chat_id, name)
        return None

    # ----- LoRA (single slot, per chat, persisted) ------------------------ #

    def get_lora_settings(self, chat_id):
        defaults = {"alias": None, "strength": 0.8}
        stored = (self.chat_settings.load().get("lora") or {}).get(str(chat_id)) or {}
        out = dict(defaults)
        out.update({k: v for k, v in stored.items() if v is not None})
        return out

    def set_lora_settings(self, chat_id, **kw):
        self.chat_settings.mutate(
            lambda s: s.setdefault("lora", {}).setdefault(str(chat_id), {}).update(kw)
        )

    def get_video_settings(self, chat_id):
        defaults = {"seconds": 2}
        stored = (self.chat_settings.load().get("video") or {}).get(str(chat_id)) or {}
        out = dict(defaults)
        out.update({k: v for k, v in stored.items() if v is not None})
        return out

    def set_video_settings(self, chat_id, **kw):
        self.chat_settings.mutate(
            lambda s: s.setdefault("video", {}).setdefault(str(chat_id), {}).update(kw)
        )

    def lora_aliases(self):
        return dict(self.config.get("lora_aliases") or {})

    def available_loras(self):
        info = self.comfy.object_info("LoraLoader", refresh=True)
        combo = ((info.get("input") or {}).get("required") or {}).get("lora_name")
        return combo[0] if combo and isinstance(combo[0], list) else []

    def inject_lora(self, workflow, chat_id):
        """Wire the selected LoRA into the model+clip chain. Returns (workflow, MsgError_or_None).

        Called BEFORE the ControlNet injection so the chain becomes
        base model → LoRA → ControlNet → sampler.
        """
        st = self.get_lora_settings(chat_id)
        alias = st.get("alias")
        if not alias:
            return workflow, None
        lora_file = self.lora_aliases().get(alias)
        if not lora_file:
            return workflow, MsgError("lora_unknown", {"name": alias, "list": ", ".join(sorted(self.lora_aliases()))})
        combo = self.available_loras()
        if lora_file not in combo:
            return workflow, MsgError("lora_file_missing", {"file": lora_file})
        sampler_id = next(
            (nid for nid, n in workflow.items() if n.get("class_type") in ("KSampler", "KSamplerAdvanced")),
            None,
        )
        clip_id = next((nid for nid, n in workflow.items() if n.get("class_type") == "CLIPTextEncode"), None)
        old_model = (workflow.get(sampler_id) or {}).get("inputs", {}).get("model") if sampler_id else None
        old_clip = (workflow.get(clip_id) or {}).get("inputs", {}).get("clip") if clip_id else None
        if not is_wire(old_model) or not is_wire(old_clip):
            return workflow, MsgError("lora_need_sampler")
        s = float(st.get("strength", 0.8))
        workflow["__lora"] = {
            "inputs": {
                "lora_name": lora_file,
                "strength_model": s,
                "strength_clip": s,
                "model": old_model,
                "clip": old_clip,
            },
            "class_type": "LoraLoader",
            "_meta": {"title": f"LoRA {alias}"},
        }
        workflow[sampler_id]["inputs"]["model"] = ["__lora", 0]
        workflow[clip_id]["inputs"]["clip"] = ["__lora", 1]
        return workflow, None

    def cmd_lora(self, chat_id, arg, chat_type="private", user_id=None):
        if chat_type != "private" and not self.is_admin(user_id):
            self.api.send_message(chat_id, self.t(chat_id, "cnet_group_admin_only"))
            return
        st = self.get_lora_settings(chat_id)
        aliases = self.lora_aliases()
        parts = arg.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""
        wf_name = self.get_chat_workflow(chat_id)

        if not sub:
            name = st["alias"] or self.t(chat_id, "lora_none")
            self.api.send_message(chat_id, self.t(
                chat_id, "lora_status", name=name, strength=st["strength"], name2=wf_name,
            ))
            return

        if sub in ("list", "список"):
            files = self.available_loras()
            lines = []
            for alias, fname in sorted(aliases.items()):
                mark = "✅" if fname in files else "❌"
                cur = " 👈 выбрана" if alias == st["alias"] else ""
                lines.append(f"{mark} {alias} — {fname}{cur}")
            extra = self.t(chat_id, "lora_file_missing", file="") if not files else ""
            self.api.send_message(
                chat_id,
                self.t(chat_id, "lora_status", name=st["alias"] or self.t(chat_id, "lora_none"),
                       strength=st["strength"], name2=wf_name) + "\n\n" + "\n".join(lines),
            )
            return

        if sub in ("off", "clear", "нет"):
            self.set_lora_settings(chat_id, alias=None)
            self.api.send_message(chat_id, self.t(chat_id, "lora_off"))
            return

        if sub == "strength":
            try:
                value = float(rest.replace(",", "."))
            except ValueError:
                self.api.send_message(chat_id, self.t(chat_id, "lora_strength_bad"))
                return
            value = max(-10.0, min(10.0, value))
            self.set_lora_settings(chat_id, strength=value)
            self.api.send_message(chat_id, self.t(chat_id, "lora_strength_set", value=value))
            return

        # otherwise `sub` is the alias to select (exact or unique substring)
        if sub in aliases:
            match_alias, match_file = sub, aliases[sub]
        else:
            hits = [a for a in aliases if sub in a.lower()]
            if len(hits) == 1:
                match_alias, match_file = hits[0], aliases[hits[0]]
            else:
                shown = ", ".join(sorted(aliases))
                self.api.send_message(chat_id, self.t(chat_id, "lora_unknown", name=sub, list=shown))
                return
        if match_file not in self.available_loras():
            self.api.send_message(chat_id, self.t(chat_id, "lora_file_missing", file=match_file))
            return
        self.set_lora_settings(chat_id, alias=match_alias)
        log.info("LoRA for chat %s set to %s", chat_id, match_alias)
        self.api.send_message(
            chat_id, self.t(chat_id, "lora_set", name=match_alias, strength=st["strength"])
        )

    def cmd_vseconds(self, chat_id, arg, chat_type="private", user_id=None):
        if chat_type != "private" and not self.is_admin(user_id):
            self.api.send_message(chat_id, self.t(chat_id, "cnet_group_admin_only"))
            return
        st = self.get_video_settings(chat_id)
        if not arg.strip():
            plan = plan_video_segments(int(st["seconds"]) * 24)
            self.api.send_message(chat_id, self.t(
                chat_id, "vseconds_status",
                seconds=st["seconds"], frames=int(st["seconds"]) * 24, segments=len(plan),
            ))
            return
        try:
            value = int(arg.strip())
        except ValueError:
            self.api.send_message(chat_id, self.t(chat_id, "vseconds_bad"))
            return
        if not 1 <= value <= 30:
            self.api.send_message(chat_id, self.t(chat_id, "vseconds_range"))
            return
        self.set_video_settings(chat_id, seconds=value)
        plan = plan_video_segments(value * 24)
        self.api.send_message(chat_id, self.t(
            chat_id, "vseconds_set", seconds=value, frames=value * 24, segments=len(plan),
        ))

    def handle_callback(self, cb):
        cb_id = cb.get("id")
        answered = False

        def answer(text=None):
            nonlocal answered
            if answered:
                return
            data = {"callback_query_id": cb_id}
            if text:
                data["text"] = text[:200]
            self.api._request("answerCallbackQuery", data=data)
            answered = True

        try:
            msg = cb.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            message_id = msg.get("message_id")
            chat_type = (msg.get("chat") or {}).get("type", "private")
            user_id = (cb.get("from") or {}).get("id")
            data = cb.get("data") or ""
            if user_id not in self.allowed_users and not self.is_admin(user_id):
                answer()
                return
            if data == "cnet_ok":
                if chat_type != "private" and not self.is_admin(user_id):
                    answer(self.t(chat_id, "cnet_group_admin_only"))
                    return
                err = self._approve_mask(chat_id)
                if err:
                    answer(self.t(chat_id, err.key, **err.kw))
                    return
                if message_id:
                    self.api._request("editMessageReplyMarkup", data={"chat_id": chat_id, "message_id": message_id})
                answer(self.t(chat_id, "cnet_mask_approved_short"))
                self.api.send_message(chat_id, self.t(chat_id, "cnet_mask_approved"))
                return
            if data == "cnet_cancel":
                self._pending_masks.pop(str(chat_id), None)
                if message_id:
                    self.api._request("editMessageReplyMarkup", data={"chat_id": chat_id, "message_id": message_id})
                answer(self.t(chat_id, "cnet_mask_cancelled_short"))
                self.api.send_message(chat_id, self.t(chat_id, "cnet_mask_cancelled"))
                return
            answer()
        except Exception:
            log.error("Callback handling failed:\n%s", traceback.format_exc())
            answer()

    def load_workflow_safe(self, chat_id=None):
        try:
            return self.load_workflow(self.get_chat_workflow(chat_id))
        except FileNotFoundError:
            return {}

    def load_active_workflow(self, chat_id):
        """The chat's currently selected workflow (for chat-facing commands)."""
        return self.load_workflow(self.get_chat_workflow(chat_id))

    def apply_overrides(self, workflow, overrides):
        """Mutate a workflow copy with persisted overrides. Returns applied prompt text."""
        for nid, params in (overrides.get("nodes") or {}).items():
            if nid not in workflow:
                log.warning("Override skipped, node %s is gone from workflow", nid)
                continue
            for param, value in params.items():
                if value == "random" and param in SEED_PARAMS:
                    value = random.getrandbits(64)
                workflow[nid].setdefault("inputs", {})[param] = value
        prompt = overrides.get("prompt")
        if prompt:
            nid = find_positive_prompt_node(workflow)
            if nid:
                workflow[nid].setdefault("inputs", {})["text"] = prompt
        return prompt or ""

    def validate_value(self, node, param, value):
        """Check value against the node schema from /object_info.

        Returns (canonical_value, MsgError_or_None).
        """
        if value == "random" and param in SEED_PARAMS:
            return value, None
        info = self.comfy.object_info(node.get("class_type", ""))
        inputs = info.get("input") or {}
        spec = (inputs.get("required") or {}).get(param) or (inputs.get("optional") or {}).get(param)
        if spec is None:
            return value, None  # not in the schema — let ComfyUI be the judge
        ptype = spec[0]
        if isinstance(ptype, list):
            opts = [str(o) for o in ptype]
            for opt in opts:
                if opt.lower() == str(value).lower():
                    return opt, None
            partial = [o for o in opts if str(value).lower() in o.lower()]
            if len(partial) == 1:
                return partial[0], None
            if len(partial) > 1:
                return value, MsgError("value_refine", {"value": value, "opts": ", ".join(partial[:10])})
            shown = ", ".join(opts[:25]) + (" …" if len(opts) > 25 else "")
            return value, MsgError("value_options", {"opts": shown})
        cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        if ptype in ("INT", "FLOAT"):
            if isinstance(value, bool):
                return value, MsgError("need_number_bool", {"ptype": ptype})
            try:
                num = float(value) if ptype == "FLOAT" else int(value)
            except (TypeError, ValueError):
                return value, MsgError("need_int" if ptype == "INT" else "need_float")
            if isinstance(num, float) and not math.isfinite(num):
                return value, MsgError("not_finite")
            lo, hi = cfg.get("min"), cfg.get("max")
            if (lo is not None and num < lo) or (hi is not None and num > hi):
                return value, MsgError("out_of_range", {"lo": lo, "hi": hi})
            return num, None
        if ptype == "BOOLEAN":
            truthy = {"true", "1", "yes", "on", "да"}
            falsy = {"false", "0", "no", "off", "нет"}
            if str(value).lower() in truthy:
                return True, None
            if str(value).lower() in falsy:
                return False, None
            return value, MsgError("need_bool")
        if ptype == "STRING":
            return str(value), None
        return value, None

    def nodes_with_param(self, workflow, param):
        return [nid for nid, node in workflow.items() if param in scalar_inputs(node)]

    def node_list(self, workflow, ids):
        return "\n".join(
            f"  • «{nid}» {workflow[nid].get('class_type')} — «{node_title(workflow[nid])}»"
            for nid in ids[:8]
        )

    def set_override(self, chat_id, workflow, target_key, param, value_text):
        if not target_key:
            matches = self.nodes_with_param(workflow, param)
            if not matches:
                self.api.send_message(
                    chat_id, self.t(chat_id, "param_not_found_anywhere", param=param)
                )
                return False
            if len(matches) > 1:
                self.api.send_message(
                    chat_id,
                    self.t(
                        chat_id, "param_multiple",
                        param=param, list=self.node_list(workflow, matches),
                    ),
                )
                return False
            node_id = matches[0]
        else:
            node_id, err = resolve_target(workflow, target_key)
            if err:
                self.send_err(chat_id, err)
                return False

        node = workflow[node_id]
        if param not in scalar_inputs(node):
            scalars = ", ".join(sorted(scalar_inputs(node))) or "(нет скалярных параметров)"
            self.api.send_message(
                chat_id,
                self.t(
                    chat_id, "param_missing",
                    node=node_id, cls=node.get("class_type"), param=param, scalars=scalars,
                ),
            )
            return False

        value = parse_value(value_text)
        canonical, err = self.validate_value(node, param, value)
        if err:
            self.api.send_message(chat_id, "⚠️ " + self.t(chat_id, err.key, **err.kw))
            return False

        old = node.get("inputs", {}).get(param)
        self.mutate_overrides(
            lambda ov: ov.setdefault("nodes", {}).setdefault(node_id, {}).update({param: canonical})
        )
        label = f"«{node_id}» {node.get('class_type')} — «{node_title(node)}»"
        self.api.send_message(
            chat_id,
            self.t(
                chat_id, "set_done",
                label=label, param=param, old=describe_value(old), new=describe_value(canonical),
            ),
        )
        return True

    # ------------------------------------------------------------------ #
    # Generation pipeline
    # ------------------------------------------------------------------ #

    def queue_workflow(self, chat_id, workflow, client_id=None):
        """POST /prompt. Returns (prompt_id, client_id, error_text)."""
        client_id = client_id or str(uuid.uuid4())
        payload = {"prompt": workflow, "client_id": client_id}
        resp = self.comfy.post("/prompt", payload, timeout=30)
        if resp is None:
            return None, client_id, self.t(chat_id, "queue_connect_fail")
        if "__http_error__" in resp:
            return None, client_id, self.format_prompt_error(chat_id, resp)
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            return None, client_id, self.t(chat_id, "unexpected_response", resp=describe_value(resp))
        return prompt_id, client_id, None

    def _listen_progress(self, prompt_id, client_id, progress_state):
        """Subscribe to ComfyUI's websocket and track sampler progress of one prompt.

        Updates progress_state {"value", "max", "done"}; degrades silently when
        the websocket library or server is unavailable (REST polling keeps working).
        """
        try:
            import websocket
        except ImportError:
            return
        ws = None
        try:
            ws = websocket.WebSocket()
            ws.settimeout(5)
            ws.connect(f"ws://{self.comfy.host}/ws?clientId={client_id}", timeout=10)
            log.info("[Telegram Bot] Progress websocket connected for %s", prompt_id)
            first_progress_logged = False
            while not progress_state.get("done"):
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue  # no events within the timeout window — keep listening
                except Exception as e:
                    log.info("[Telegram Bot] Progress websocket closed for %s: %s", prompt_id, e)
                    break  # connection died — spinning on recv would burn CPU
                if isinstance(raw, bytes):
                    continue  # binary preview frames
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mtype = msg.get("type")
                data = msg.get("data") or {}
                if mtype == "progress" and data.get("prompt_id") == prompt_id:
                    try:
                        progress_state["value"] = int(data.get("value", 0))
                        progress_state["max"] = int(data.get("max", 0))
                    except (TypeError, ValueError):
                        pass
                    if not first_progress_logged:
                        first_progress_logged = True
                        log.info(
                            "[Telegram Bot] Progress events received for %s (%s/%s)",
                            prompt_id, progress_state["value"], progress_state["max"],
                        )
                elif mtype == "executing" and data.get("prompt_id") == prompt_id and data.get("node") is None:
                    progress_state["done"] = True
                    break
        except Exception as e:
            log.info("[Telegram Bot] Progress websocket unavailable for %s: %s", prompt_id, e)
        finally:
            progress_state["done"] = True
            try:
                if ws is not None:
                    ws.close()
            except Exception:
                pass

    def format_prompt_error(self, chat_id, resp):
        parts = [self.t(chat_id, "prompt_rejected", code=resp["__http_error__"])]
        err = resp.get("error") or {}
        if err.get("message"):
            parts.append(self.t(chat_id, "prompt_error_line", message=err["message"]))
        for nid, details in list((resp.get("node_errors") or {}).items())[:5]:
            messages = "; ".join(
                e.get("message", "?") for e in (details.get("errors") or [])[:3]
            )
            parts.append(self.t(chat_id, "prompt_node_error_line", node=nid, messages=messages))
        return "\n".join(parts)[:3500]

    def progress_detail(self, chat_id, elapsed, running, pending, pending_ids, prompt_id, progress_state):
        """The status-message detail part: queue position or step progress with ETA."""
        if running and progress_state["max"] > 0 and progress_state["value"] > 0:
            # value and max come from a websocket thread; clamp for the transient
            # moment when a new node's max arrives before its value
            value = min(progress_state["value"], progress_state["max"])
            fraction = value / progress_state["max"]
            detail = self.t(chat_id, "progress_step", value=value, max=progress_state["max"])
            if fraction < 1:
                eta = max(1, int(elapsed * (1 - fraction) / fraction))
                detail += " · " + self.t(chat_id, "progress_eta", eta=eta)
            return detail
        if running:
            return self.t(chat_id, "place_running")
        if pending:
            return self.t(
                chat_id, "place_queue",
                pos=pending_ids.index(prompt_id) + 1, total=len(pending_ids),
            )
        return self.t(chat_id, "place_waiting")

    def track_and_deliver(self, chat_id, prompt_id, prompt_text, workflow, client_id=None):
        """Poll /history, keep the user updated, deliver ALL images as an album."""
        timeout = int(self.config.get("generation_timeout", 1800))
        # Telegram rate limits edits like messages: keep at least 3s between them
        edit_every = max(3, int(self.config.get("progress_edit_interval", 5)))
        started = time.time()
        status_msg_id = self.api.send_message(chat_id, self.t(chat_id, "generating"))
        last_edit = time.time()

        progress_state = {"value": 0, "max": 0, "done": False}
        if client_id and getattr(self.comfy, "host", None):
            threading.Thread(
                target=self._listen_progress,
                args=(prompt_id, client_id, progress_state),
                daemon=True,
            ).start()

        history_entry = None
        vanished_since = None
        running = pending = False
        pending_ids = []
        while time.time() - started < timeout:
            time.sleep(2)
            history = self.comfy.get(f"/history/{prompt_id}", timeout=15)
            if history and prompt_id in history:
                history_entry = history[prompt_id]
                break

            queue = self.comfy.get("/queue", timeout=10) or {}
            pending_ids = [q[1] for q in queue.get("queue_pending", [])]
            running = prompt_id in [q[1] for q in queue.get("queue_running", [])]
            pending = prompt_id in pending_ids

            if not running and not pending:
                # A queued/running job missing from both queue and history was
                # cancelled (/stop, /clearqueue) or the server restarted mid-run.
                if vanished_since is None:
                    vanished_since = time.time()
                elif time.time() - vanished_since > 10:
                    progress_state["done"] = True
                    self.api.edit_message(
                        chat_id, status_msg_id, self.t(chat_id, "job_vanished")
                    )
                    return
            else:
                vanished_since = None

            if status_msg_id and time.time() - last_edit >= edit_every:
                elapsed = int(time.time() - started)
                detail = self.progress_detail(
                    chat_id, elapsed, running, pending, pending_ids, prompt_id, progress_state
                )
                self.api.edit_message(
                    chat_id, status_msg_id,
                    self.t(chat_id, "generating_status", elapsed=elapsed, detail=detail),
                )
                last_edit = time.time()

        progress_state["done"] = True

        if history_entry is None:
            self.api.edit_message(
                chat_id, status_msg_id,
                self.t(chat_id, "wait_timeout", minutes=timeout // 60),
            )
            return

        errored = (history_entry.get("status") or {}).get("status_str") == "error"
        images = collect_history_images(history_entry)
        media = []
        for img in images:
            data = self.comfy.fetch_image(img["filename"], img["subfolder"], img["type"])
            if not data:
                continue
            ext = os.path.splitext(img["filename"])[1].lower().lstrip(".") or "png"
            if ext not in VIDEO_EXTS:
                data = self.maybe_recompress(data)
            media.append((data, ext))

        if not media:
            key = "error_no_images" if errored else "no_images"
            self.api.edit_message(chat_id, status_msg_id, self.t(chat_id, key))
            return

        elapsed = int(time.time() - started)
        if errored:
            self.api.edit_message(
                chat_id, status_msg_id,
                self.t(chat_id, "done_error", elapsed=elapsed, count=len(media)),
            )
            caption = (
                self.t(chat_id, "caption_error", text=prompt_text)
                if prompt_text else self.t(chat_id, "caption_error_plain")
            )
        else:
            self.api.edit_message(
                chat_id, status_msg_id,
                self.t(chat_id, "done", elapsed=elapsed, count=len(media)),
            )
            caption = (
                self.t(chat_id, "caption_ok", text=prompt_text)
                if prompt_text else self.t(chat_id, "caption_ok_plain")
            )
        self.deliver_media(chat_id, media, caption)

        self.state.save({
            "last": {
                "prompt_id": prompt_id,
                "chat_id": chat_id,
                "prompt_text": prompt_text,
                "workflow": workflow,
                "images": images,
                "errored": errored,
                "finished_at": time.time(),
                "elapsed": elapsed,
            }
        })

    def run_video_chain(self, chat_id, base_workflow, plan, first_image_name, seconds, prompt_text):
        """Generate a long video in <=81-frame segments, chaining via the last frame."""
        loader_id = next(
            (nid for nid, n in base_workflow.items() if n.get("class_type") == "LoadImage"), None
        )
        latent_id = next(
            (nid for nid, n in base_workflow.items() if n.get("class_type") == "Wan22ImageToVideoLatent"), None
        )
        if not loader_id or not latent_id:
            self.api.send_message(chat_id, self.t(chat_id, "lora_need_sampler"))
            return
        status_msg_id = self.api.send_message(
            chat_id,
            self.t(chat_id, "video_segment_progress", seconds=seconds, i=1, n=len(plan), elapsed=0),
        )
        seed = random.getrandbits(64)
        blobs = []
        start_name = first_image_name
        t_start = time.time()
        for i, length in enumerate(plan, 1):
            wf = copy.deepcopy(base_workflow)
            wf[latent_id]["inputs"]["length"] = length
            if i == 1 and not start_name:
                wf[latent_id]["inputs"].pop("start_image", None)  # T2V first segment
                wf.pop(loader_id, None)
            else:
                if loader_id in wf:
                    wf[loader_id]["inputs"]["image"] = start_name
                else:
                    wf[loader_id] = {"inputs": {"image": start_name}, "class_type": "LoadImage"}
                wf[latent_id]["inputs"]["start_image"] = [loader_id, 0]
            for n in wf.values():
                if n.get("class_type") == "AdvancedSeedGenerator":
                    n["inputs"]["mode"] = "fixed"
                    n["inputs"]["seed"] = seed
            prompt_id, client_id, err = self.queue_workflow(chat_id, wf)
            if err:
                self.api.send_message(chat_id, f"⚠️ {err}")
                return
            entry = None
            seg_t0 = time.time()
            while time.time() - seg_t0 < 1500:
                time.sleep(5)
                h = self.comfy.get(f"/history/{prompt_id}", timeout=15)
                if h and prompt_id in h:
                    entry = h[prompt_id]
                    break
            st = (entry or {}).get("status", {})
            if (st.get("status_str")) != "success":
                self.api.send_message(chat_id, self.t(
                    chat_id, "video_chain_failed", i=i, n=len(plan), reason="ошибка генерации",
                ))
                return
            mp4 = None
            for img in collect_history_images(entry):
                if os.path.splitext(img["filename"])[1].lower() in VIDEO_EXTS:
                    mp4 = self.comfy.fetch_image(img["filename"], img["subfolder"], img["type"])
                    break
            if not mp4:
                self.api.send_message(chat_id, self.t(
                    chat_id, "video_chain_failed", i=i, n=len(plan), reason="файл не найден",
                ))
                return
            blobs.append(mp4)
            if i < len(plan):
                last_png = video_last_frame_png(mp4)
                if not last_png:
                    self.api.send_message(chat_id, self.t(
                        chat_id, "video_chain_failed", i=i, n=len(plan), reason="кадр не извлечён",
                    ))
                    return
                start_name = self.comfy.upload_image(last_png, f"tg_chain_{uuid.uuid4().hex}.png")
                if not start_name:
                    self.api.send_message(chat_id, self.t(
                        chat_id, "video_chain_failed", i=i, n=len(plan), reason="upload",
                    ))
                    return
            if status_msg_id and i < len(plan):
                self.api.edit_message(chat_id, status_msg_id, self.t(
                    chat_id, "video_segment_progress",
                    seconds=seconds, i=i + 1, n=len(plan), elapsed=int(time.time() - t_start),
                ))
        self.api.edit_message(chat_id, status_msg_id, self.t(chat_id, "video_assembling"))
        final = assemble_mp4(blobs, fps=24)
        if not final:
            self.api.send_message(chat_id, self.t(chat_id, "video_chain_failed", i=0, n=len(plan), reason="assembly"))
            return
        caption = f"🎥 {prompt_text} · {seconds}с · {len(plan)} сегм." if prompt_text else f"🎥 {seconds}с · {len(plan)} сегм."
        self.api.send_video(chat_id, final, caption, filename="wan22_chain.mp4")
        log.info("Chained video delivered: %s segments, %ss", len(plan), seconds)

    def deliver_media(self, chat_id, media, caption):
        """1 image -> sendPhoto; 2+ -> albums of 10 with sequential fallback."""
        if not media:
            return
        if len(media) == 1:
            blob, ext = media[0]
            self._send_one(chat_id, blob, ext, caption)
            return
        if all(ext not in VIDEO_EXTS for _, ext in media):
            ok = True
            for index, chunk in enumerate(chunks([b for b, _ in media], 10)):
                sent = self.api.send_album(chat_id, chunk, caption if index == 0 else "")
                if not sent:
                    ok = False
                    for j, blob in enumerate(chunk):  # fallback: one by one
                        first_of_all = index == 0 and j == 0
                        self.api.send_photo(chat_id, blob, caption if first_of_all else "")
                        time.sleep(1)
                time.sleep(1)  # be gentle with rate limits between albums
            if not ok:
                self.api.send_message(chat_id, self.t(chat_id, "album_partial_fail"))
            return
        for index, (blob, ext) in enumerate(media):  # mixed media: videos go one by one
            self._send_one(chat_id, blob, ext, caption if index == 0 else "")
            time.sleep(1)

    def _send_one(self, chat_id, blob, ext, caption):
        if ext in VIDEO_EXTS:
            if self.api.send_video(chat_id, blob, caption, filename=f"video.{ext}") is None:
                time.sleep(2)
                self.api.send_video(chat_id, blob, caption, filename=f"video.{ext}")
            return
        if self.api.send_photo(chat_id, blob, caption) is None:
            time.sleep(2)
            self.api.send_photo(chat_id, blob, caption)

    @staticmethod
    def maybe_recompress(blob):
        """Telegram photo limit is 10 MB — re-encode oversized PNGs to JPEG."""
        if len(blob) <= 9_500_000:
            return blob
        try:
            import io

            from PIL import Image
            img = Image.open(io.BytesIO(blob))
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
        except Exception as e:
            log.warning("Cannot recompress large image: %s", e)
            return blob

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    def cmd_start(self, chat_id, arg):
        self.api.send_message(chat_id, self.t(chat_id, "start_text"))

    def cmd_help(self, chat_id, arg):
        self.api.send_message(chat_id, self.t(chat_id, "help_text"), parse_mode="HTML")

    def cmd_lang(self, chat_id, arg, chat_type="private", user_id=None):
        arg = arg.strip().lower()
        available = ", ".join(f"{code} — {name}" for code, name in LANGUAGES.items())
        if not arg:
            cur = self.get_lang(chat_id)
            self.api.send_message(
                chat_id,
                "\n".join([
                    self.t(chat_id, "lang_current", lang=LANGUAGES.get(cur, cur)),
                    self.t(chat_id, "lang_available", langs=available),
                    self.t(chat_id, "lang_usage"),
                ]),
            )
            return
        if arg not in LANGUAGES:
            self.api.send_message(
                chat_id, self.t(chat_id, "lang_unknown", lang=arg, available=available)
            )
            return
        if chat_type != "private" and not self.is_admin(user_id):
            self.api.send_message(chat_id, self.t(chat_id, "lang_group_admin_only"))
            return
        self.set_chat_lang(chat_id, arg)
        self.api.send_message(chat_id, self.t(chat_id, "lang_set", lang=LANGUAGES[arg]))

    def cmd_generate(self, chat_id, arg, image_ref=None):
        text = arg.strip()
        overrides = self.overrides.load()
        if not text:
            text = overrides.get("prompt") or ""
            if not text:
                self.api.send_message(chat_id, self.t(chat_id, "usage_generate"))
                return
        workflow_name = self.get_chat_workflow(chat_id)
        try:
            workflow = self.load_workflow(workflow_name)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        self.apply_overrides(workflow, overrides)
        nid = find_positive_prompt_node(workflow)
        if not nid:
            self.api.send_message(chat_id, self.t(chat_id, "no_prompt_node"))
            return
        workflow[nid]["inputs"]["text"] = text

        # img2img media handling
        img_node = find_load_image_node(workflow)
        main_image_name = None
        if image_ref and img_node:
            blob, dl_err = self.api.download_file(image_ref["file_id"])
            if not blob:
                self.api.send_message(chat_id, self.t(chat_id, dl_err.key, **dl_err.kw))
                return
            filename = f"tg_{uuid.uuid4().hex}.{image_ref['ext']}"
            stored_name = self.comfy.upload_image(blob, filename)
            if not stored_name:
                self.api.send_message(chat_id, self.t(chat_id, "img_upload_fail"))
                return
            workflow[img_node]["inputs"]["image"] = stored_name
            main_image_name = stored_name
            log.info("Image %s uploaded for %s", stored_name, workflow_name)
        elif image_ref and not img_node:
            self.api.send_message(
                chat_id, self.t(chat_id, "img_unused", name=workflow_name)
            )
        elif img_node and not image_ref and not self.is_video_workflow(workflow):
            self.api.send_message(
                chat_id, self.t(chat_id, "img_need", name=workflow_name)
            )
            return
        if self.is_video_workflow(workflow) and img_node and not image_ref:
            # TI2V text-only mode: no start image -> drop the wire, latent stays pure noise
            workflow.pop(img_node, None)
            for n in workflow.values():
                n.get("inputs", {}).pop("start_image", None)

        # LoRA patch (both flows) — wired before ControlNet so the chain is
        # base model → LoRA → ControlNet → sampler
        if self.get_lora_settings(chat_id).get("alias"):
            workflow, lora_err = self.inject_lora(workflow, chat_id)
            if lora_err:
                self.send_err(chat_id, lora_err)
                return
            log.info("LoRA injected for chat %s", chat_id)

        # ControlNet patch (image flows only): requires an approved mask
        if self.get_cnet_settings(chat_id).get("enabled"):
            if self.is_video_workflow(workflow):
                self.api.send_message(chat_id, self.t(chat_id, "cnet_video_skip"))
            else:
                workflow, cnet_err = self.inject_controlnet(workflow, chat_id)
                if cnet_err:
                    self.send_err(chat_id, cnet_err)
                    return
            # video workflow: split the duration into <=81-frame segments and chain them
        if self.is_video_workflow(workflow):
            vset = self.get_video_settings(chat_id)
            plan = plan_video_segments(int(vset.get("seconds", 2)) * 24)
            latent_id = next(
                (nid for nid, n in workflow.items() if n.get("class_type") == "Wan22ImageToVideoLatent"),
                None,
            )
            if latent_id and len(plan) == 1:
                workflow[latent_id]["inputs"]["length"] = plan[0]
                if not main_image_name:
                    workflow[latent_id]["inputs"].pop("start_image", None)
            elif latent_id:
                threading.Thread(
                    target=self.run_video_chain,
                    args=(chat_id, workflow, plan, main_image_name, int(vset.get("seconds", 2)), text),
                    daemon=True,
                ).start()
                return

        prompt_id, client_id, err = self.queue_workflow(chat_id, workflow)
        if err:
            self.api.send_message(chat_id, f"⚠️ {err}")
            return
        log.info("Queued prompt %s (chat %s): %s", prompt_id, chat_id, text[:80])
        threading.Thread(
            target=self.track_and_deliver,
            args=(chat_id, prompt_id, text, copy.deepcopy(workflow), client_id),
            daemon=True,
        ).start()

    def cmd_workflow(self, chat_id, arg, chat_type="private", user_id=None):
        name = arg.strip().lower()
        available = self.available_workflows()
        if not name:
            current = self.get_chat_workflow(chat_id)
            self.api.send_message(
                chat_id,
                self.t(
                    chat_id, "workflow_usage",
                    name=current, list=", ".join(sorted(available)),
                ),
            )
            return
        if name not in available:
            self.api.send_message(
                chat_id,
                self.t(chat_id, "workflow_unknown", name=name, list=", ".join(sorted(available))),
            )
            return
        if chat_type != "private" and not self.is_admin(user_id):
            self.api.send_message(chat_id, self.t(chat_id, "lang_group_admin_only"))
            return
        self.set_chat_workflow(chat_id, name)
        log.info("Workflow for chat %s set to %s", chat_id, name)
        hint = ""
        try:
            fresh = self.load_workflow(name)
            if any("denoise" in n.get("inputs", {}) for n in fresh.values()):
                hint = "\n" + self.t(chat_id, "workflow_denoise_hint")
        except FileNotFoundError:
            pass
        self.api.send_message(chat_id, self.t(chat_id, "workflow_set", name=name) + hint)

    def cmd_tips(self, chat_id, arg):
        """Prompting guide for the chat's active workflow."""
        workflow = self.load_active_workflow(chat_id)
        classes = [n.get("class_type", "") for n in workflow.values()]
        if any("Wan" in c for c in classes):
            key = "prompting_video"
        elif any(
            "z_image" in str(n.get("inputs", {}).get("unet_name", "")).lower()
            for n in workflow.values()
            if n.get("class_type") == "UNETLoader"
        ):
            key = "prompting_zimage"
        else:
            key = "prompting_generic"
        self.api.send_message(
            chat_id,
            self.t(chat_id, key) + "\n\n" + self.t(chat_id, "tips_usage"),
        )

    def cmd_prompt(self, chat_id, arg):
        if not arg.strip():
            self.api.send_message(chat_id, self.t(chat_id, "usage_prompt"))
            return
        self.mutate_overrides(lambda ov: ov.update({"prompt": arg.strip()}))
        self.api.send_message(chat_id, self.t(chat_id, "prompt_saved", text=arg.strip()))

    def cmd_nodes(self, chat_id, arg):
        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        lines = [f"«{nid}» {node.get('class_type')} — «{node_title(node)}»" for nid, node in workflow.items()]
        n_over = len(self.overrides.load().get("nodes") or {})
        self.api.send_message(
            chat_id,
            self.t(chat_id, "nodes_title", name=self.get_chat_workflow(chat_id)) + "\n" + "\n".join(lines)
            + self.t(chat_id, "overrides_count", count=n_over),
        )

    def cmd_params(self, chat_id, arg):
        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        if not arg.strip():
            overrides = self.overrides.load()
            prompt = overrides.get("prompt")
            nodes = overrides.get("nodes") or {}
            if not prompt and not nodes:
                self.api.send_message(chat_id, self.t(chat_id, "settings_empty"))
                return
            lines = [self.t(chat_id, "settings_title")]
            if prompt:
                lines.append(self.t(chat_id, "settings_prompt_line", text=prompt[:200]))
            for nid, params in nodes.items():
                cls = workflow.get(nid, {}).get("class_type", "?")
                for p, v in params.items():
                    lines.append(f"«{nid}» {cls}: {p} = {describe_value(v)}")
            self.api.send_message(chat_id, "\n".join(lines)[:4000])
            return

        node_id, err = resolve_target(workflow, arg)
        if err:
            self.send_err(chat_id, err)
            return
        node = workflow[node_id]
        node_over = (self.overrides.load().get("nodes") or {}).get(node_id) or {}
        lines = [
            self.t(
                chat_id, "params_header",
                node=node_id, cls=node.get("class_type"), title=node_title(node),
                wf=self.get_chat_workflow(chat_id),
            )
        ]
        info = self.comfy.object_info(node.get("class_type", ""))
        required = (info.get("input") or {}).get("required") or {}
        for p, v in scalar_inputs(node).items():
            eff = node_over.get(p, v)
            line = f"  • {p} = {describe_value(eff)}"
            if p in node_over:
                line += self.t(chat_id, "overridden_marker")
            spec = required.get(p)
            if spec and isinstance(spec[0], list) and len(spec[0]) <= 12:
                line += self.t(chat_id, "variants_suffix", opts=", ".join(map(str, spec[0])))
            lines.append(line)
        wires = [k for k, v in node.get("inputs", {}).items() if is_wire(v)]
        if wires:
            lines.append(self.t(chat_id, "wires_suffix", wires=", ".join(wires)))
        lines.append(self.t(chat_id, "set_hint", node=node_id))
        self.api.send_message(chat_id, "\n".join(lines)[:4000])

    def cmd_set(self, chat_id, arg):
        parts = arg.split(None, 1)
        if len(parts) < 2:
            self.api.send_message(chat_id, self.t(chat_id, "set_usage"))
            return
        target_token, value_text = parts
        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        target_key, param = None, target_token
        if "." in target_token:
            candidate_node, candidate_param = target_token.split(".", 1)
            node_id, err = resolve_target(workflow, candidate_node)
            if err is None and candidate_param in scalar_inputs(workflow[node_id]):
                target_key, param = candidate_node, candidate_param
        self.set_override(chat_id, workflow, target_key, param, value_text)

    def cmd_unset(self, chat_id, arg):
        token = arg.strip()
        if not token:
            self.api.send_message(chat_id, self.t(chat_id, "unset_usage"))
            return
        candidates = None
        if "." in token:
            node_key, param = token.split(".", 1)
            node_id, _ = resolve_target(self.load_workflow_safe(chat_id), node_key)
            candidates = [node_id] if node_id else [node_key]
            first = param
        else:
            first = token

        def mutate(ov):
            nodes = ov.setdefault("nodes", {})
            removed = 0
            for nid in list(nodes):
                if candidates is not None:
                    if nid in candidates and first in nodes[nid]:
                        del nodes[nid][first]
                        removed += 1
                elif first in nodes[nid]:
                    del nodes[nid][first]
                    removed += 1
                if nid in nodes and not nodes[nid]:
                    del nodes[nid]
            return removed

        removed = self.mutate_overrides(mutate)
        if removed:
            self.api.send_message(chat_id, self.t(chat_id, "unset_done_count", count=removed))
        else:
            self.api.send_message(chat_id, self.t(chat_id, "unset_none"))

    def cmd_settings(self, chat_id, arg):
        self.cmd_params(chat_id, "")

    def cmd_reset(self, chat_id, arg):
        self.overrides.save({"prompt": None, "nodes": {}})
        self.api.send_message(chat_id, self.t(chat_id, "reset_done"))

    # ----- quick parameter shortcuts ----------------------------------- #

    def _shortcut(self, chat_id, param, value_text, cmd):
        if not value_text:
            self.api.send_message(chat_id, self.t(chat_id, "usage_shortcut", cmd=cmd))
            return
        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        self.set_override(chat_id, workflow, None, param, value_text)

    def cmd_steps(self, chat_id, arg):
        self._shortcut(chat_id, "steps", arg, "steps")

    def cmd_cfg(self, chat_id, arg):
        self._shortcut(chat_id, "cfg", arg, "cfg")

    def cmd_width(self, chat_id, arg):
        self._shortcut(chat_id, "width", arg, "width")

    def cmd_height(self, chat_id, arg):
        self._shortcut(chat_id, "height", arg, "height")

    def cmd_batch(self, chat_id, arg):
        # txt2img: batch_size on the empty latent; img2img: amount on RepeatLatentBatch
        if not arg.strip():
            self.api.send_message(chat_id, self.t(chat_id, "usage_shortcut", cmd="batch"))
            return
        workflow = self.load_active_workflow(chat_id)
        for param in ("batch_size", "amount"):
            if self.nodes_with_param(workflow, param):
                self.set_override(chat_id, workflow, None, param, arg)
                return
        self.api.send_message(chat_id, self.t(chat_id, "param_not_found_anywhere", param="batch"))

    def cmd_sampler(self, chat_id, arg):
        self._shortcut(chat_id, "sampler_name", arg, "sampler")

    def cmd_scheduler(self, chat_id, arg):
        self._shortcut(chat_id, "scheduler", arg, "scheduler")

    def cmd_denoise(self, chat_id, arg):
        self._shortcut(chat_id, "denoise", arg, "denoise")

    def cmd_seed(self, chat_id, arg):
        value = arg.strip().lower()
        if not value:
            self.api.send_message(chat_id, self.t(chat_id, "seed_usage"))
            return

        mode = None
        seed_val = None
        if value in ("random", "increment", "decrement"):
            mode = value
        else:
            try:
                seed_val = int(value)
            except ValueError:
                self.api.send_message(chat_id, self.t(chat_id, "seed_not_number"))
                return
            if not 0 <= seed_val <= SEED_MAX:
                self.api.send_message(chat_id, self.t(chat_id, "seed_range"))
                return

        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        seed_nodes = [
            nid for nid, node in workflow.items()
            if "seed" in node.get("class_type", "").lower() and "mode" in node.get("inputs", {})
        ]
        if seed_nodes:
            def mutate(ov):
                for nid in seed_nodes:
                    params = ov.setdefault("nodes", {}).setdefault(nid, {})
                    params["mode"] = mode if mode else "fixed"
                    if mode:
                        params.pop("seed", None)
                    else:
                        params["seed"] = seed_val
            self.mutate_overrides(mutate)
            what = self.t(chat_id, f"seed_{mode}") if mode else str(seed_val)
            self.api.send_message(
                chat_id, self.t(chat_id, "seed_set", what=what, nodes="», «".join(seed_nodes))
            )
            return

        # No seed generator node: override the scalar seed directly ("random" is applied per run).
        targets = sorted(set(self.nodes_with_param(workflow, "seed") + self.nodes_with_param(workflow, "noise_seed")))
        if not targets:
            self.api.send_message(chat_id, self.t(chat_id, "seed_no_node"))
            return
        if mode in ("increment", "decrement"):
            self.api.send_message(chat_id, self.t(chat_id, "seed_modes_unavailable"))
            return

        def mutate(ov):
            for nid in targets:
                param = "seed" if "seed" in scalar_inputs(workflow[nid]) else "noise_seed"
                ov.setdefault("nodes", {}).setdefault(nid, {})[param] = mode if mode else seed_val
        self.mutate_overrides(mutate)
        what = self.t(chat_id, "seed_random") if mode == "random" else str(seed_val)
        self.api.send_message(
            chat_id, self.t(chat_id, "seed_set_multi", what=what, nodes="», «".join(targets))
        )

    def _model_param(self, workflow):
        for param in ("unet_name", "ckpt_name", "checkpoint_name"):
            nids = self.nodes_with_param(workflow, param)
            if nids:
                return param, nids
        return None, []

    def cmd_model(self, chat_id, arg):
        name = arg.strip()
        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        param, nids = self._model_param(workflow)
        if not param:
            self.api.send_message(chat_id, self.t(chat_id, "model_none"))
            return
        node = workflow[nids[0]]
        if not name:
            self.api.send_message(
                chat_id,
                self.t(
                    chat_id, "model_current",
                    param=param, value=describe_value(node["inputs"].get(param)),
                ),
            )
            return
        self.set_override(chat_id, workflow, nids[0], param, name)

    def cmd_models(self, chat_id, arg):
        try:
            workflow = self.load_active_workflow(chat_id)
        except FileNotFoundError as e:
            self.api.send_message(chat_id, self.t(chat_id, "workflow_missing", path=e))
            return
        param, nids = self._model_param(workflow)
        if not param:
            self.api.send_message(chat_id, self.t(chat_id, "model_none"))
            return
        info = self.comfy.object_info(workflow[nids[0]].get("class_type", ""))
        spec = ((info.get("input") or {}).get("required") or {}).get(param)
        opts = spec[0] if spec and isinstance(spec[0], list) else []
        if not opts:
            self.api.send_message(chat_id, self.t(chat_id, "models_empty"))
            return
        lines = [self.t(chat_id, "models_title", param=param, count=len(opts))]
        lines += [f"  {i}. {o}" for i, o in enumerate(opts[:60], 1)]
        if len(opts) > 60:
            lines.append("  …")
        self.api.send_message(chat_id, "\n".join(lines)[:4000])

    # ----- server control ---------------------------------------------- #

    def cmd_status(self, chat_id, arg):
        stats = self.comfy.get("/system_stats")
        queue = self.comfy.get("/queue")
        if stats is None and queue is None:
            self.api.send_message(
                chat_id, self.t(chat_id, "server_no_response", host=self.config["comfy_host"])
            )
            return
        sysinfo = (stats or {}).get("system") or {}
        lines = [self.t(chat_id, "status_title")]
        if sysinfo.get("comfyui_version"):
            lines.append(self.t(chat_id, "status_version", version=sysinfo["comfyui_version"]))
        if sysinfo.get("ram_total") and sysinfo.get("ram_free"):
            lines.append(self.t(
                chat_id, "status_ram",
                free=sysinfo["ram_free"] // (1 << 30), total=sysinfo["ram_total"] // (1 << 30),
            ))
        for d in ((stats or {}).get("devices") or [])[:2]:
            lines.append(self.t(
                chat_id, "status_gpu",
                name=d.get("name", "GPU"),
                free=(d.get("vram_free") or 0) // (1 << 30),
                total=(d.get("vram_total") or 0) // (1 << 30),
            ))
        running = len((queue or {}).get("queue_running") or [])
        pending = len((queue or {}).get("queue_pending") or [])
        lines.append(self.t(chat_id, "status_queue_line", running=running, pending=pending))
        lines.append(self.t(
            chat_id, "status_overrides_line",
            count=len(self.overrides.load().get("nodes") or {}),
        ))
        with _state_lock:
            state = dict(_bot_state)
        lines.append(self.t(
            chat_id, "status_bot_line",
            uptime=format_uptime(time.time() - state["started_at"]),
            restarts=state["restarts"],
            updates=state["updates"],
        ))
        self.api.send_message(chat_id, "\n".join(lines))

    def cmd_queue(self, chat_id, arg):
        queue = self.comfy.get("/queue")
        if queue is None:
            self.api.send_message(
                chat_id, self.t(chat_id, "server_no_response", host=self.config["comfy_host"])
            )
            return
        running = queue.get("queue_running") or []
        pending = queue.get("queue_pending") or []
        if not running and not pending:
            self.api.send_message(chat_id, self.t(chat_id, "queue_empty"))
            return
        lines = [self.t(chat_id, "queue_title")]
        for item in running:
            lines.append(self.t(chat_id, "queue_running_item", id=str(item[1])[:8]))
        for item in pending:
            lines.append(self.t(chat_id, "queue_pending_item", id=str(item[1])[:8]))
        self.api.send_message(chat_id, "\n".join(lines))

    def cmd_stop(self, chat_id, arg):
        result = self.comfy.post("/interrupt", timeout=10)
        if result is None:
            self.api.send_message(chat_id, self.t(chat_id, "interrupt_fail"))
        else:
            self.api.send_message(chat_id, self.t(chat_id, "interrupt_ok"))

    def cmd_clearqueue(self, chat_id, arg):
        result = self.comfy.post("/queue", {"clear": True}, timeout=10)
        if result is None:
            self.api.send_message(chat_id, self.t(chat_id, "interrupt_fail"))
        else:
            self.api.send_message(chat_id, self.t(chat_id, "clear_ok"))

    def cmd_last(self, chat_id, arg):
        last = (self.state.load().get("last")) or {}
        if not last:
            self.api.send_message(chat_id, self.t(chat_id, "last_none"))
            return
        images = last.get("images") or []
        if last.get("prompt_id"):
            history = self.comfy.get(f"/history/{last['prompt_id']}", timeout=15) or {}
            fresh = collect_history_images(history.get(last["prompt_id"]))
            if fresh:
                images = fresh
        media = []
        for img in images[:10]:
            data = self.comfy.fetch_image(img["filename"], img["subfolder"], img["type"])
            if data:
                ext = os.path.splitext(img["filename"])[1].lower().lstrip(".") or "png"
                media.append((self.maybe_recompress(data) if ext not in VIDEO_EXTS else data, ext))
        if not media:
            self.api.send_message(chat_id, self.t(chat_id, "last_unavailable"))
            return
        caption = (
            self.t(chat_id, "caption_ok", text=last.get("prompt_text", ""))
            if last.get("prompt_text") else self.t(chat_id, "last_caption_plain")
        )
        self.deliver_media(chat_id, media, caption)

    def cmd_regen(self, chat_id, arg):
        last = (self.state.load().get("last")) or {}
        workflow = last.get("workflow")
        if not workflow:
            self.api.send_message(chat_id, self.t(chat_id, "regen_none"))
            return
        workflow = copy.deepcopy(workflow)
        for nid, node in workflow.items():
            cls = node.get("class_type", "")
            if "seed" in cls.lower() and "mode" in node.get("inputs", {}):
                node["inputs"]["mode"] = "random"
            for p in SEED_PARAMS:
                if p in scalar_inputs(node):
                    node["inputs"][p] = random.getrandbits(64)
        prompt_id, client_id, err = self.queue_workflow(chat_id, workflow)
        if err:
            self.api.send_message(chat_id, f"⚠️ {err}")
            return
        text = last.get("prompt_text", "")
        log.info("Regen queued %s", prompt_id)
        caption_text = f"{text} {self.t(chat_id, 'regen_suffix')}" if text else self.t(chat_id, "regen_suffix")
        threading.Thread(
            target=self.track_and_deliver,
            args=(chat_id, prompt_id, caption_text, workflow, client_id),
            daemon=True,
        ).start()

    # ----- user management (admins only) -------------------------------- #

    @staticmethod
    def _parse_user_id(arg, reply_user_id):
        """Numeric ID from the argument, or the user being replied to."""
        arg = (arg or "").strip().lstrip("@")
        if arg.isdigit():
            return int(arg), None
        if arg:
            return None, MsgError("user_id_needed")
        if reply_user_id:
            return reply_user_id, None
        return None, MsgError("reply_or_id_needed")

    def cmd_id(self, chat_id, user_id):
        self.api.send_message(
            chat_id, self.t(chat_id, "id_reply", user_id=user_id, chat_id=chat_id)
        )

    def cmd_users(self, chat_id, arg):
        lines = [self.t(chat_id, "users_title")]
        for aid in sorted(self.admins):
            lines.append(self.t(chat_id, "users_admin_item", id=aid))
        for uid in sorted(self.allowed_users):
            if uid in self.admins:
                continue
            lines.append(self.t(chat_id, "users_item", id=uid))
        lines.append(self.t(chat_id, "users_footer"))
        self.api.send_message(chat_id, "\n".join(lines))

    def cmd_adduser(self, chat_id, arg, reply_user_id=None):
        target, err = self._parse_user_id(arg, reply_user_id)
        if err:
            self.send_err(chat_id, err)
            return
        if target in self.admins:
            self.api.send_message(chat_id, self.t(chat_id, "user_is_admin", id=target))
            return
        if target in self.allowed_users:
            self.api.send_message(chat_id, self.t(chat_id, "user_already_allowed", id=target))
            return

        def mutate(cfg):
            cfg.setdefault("allowed_users", []).append(target)

        self.update_config(mutate)
        log.info("Admin allowed user %s", target)
        self.api.send_message(chat_id, self.t(chat_id, "user_added", id=target))

    def cmd_deluser(self, chat_id, arg, reply_user_id=None):
        target, err = self._parse_user_id(arg, reply_user_id)
        if err:
            self.send_err(chat_id, err)
            return
        if target in self.admins:
            self.api.send_message(chat_id, self.t(chat_id, "admin_protected"))
            return
        if target not in self.allowed_users:
            self.api.send_message(chat_id, self.t(chat_id, "user_not_listed", id=target))
            return

        def mutate(cfg):
            cfg["allowed_users"] = [u for u in (cfg.get("allowed_users") or []) if u != target]

        self.update_config(mutate)
        log.info("Admin removed user %s", target)
        self.api.send_message(chat_id, self.t(chat_id, "user_deleted", id=target))


# --------------------------------------------------------------------------- #
# Supervisor + watchdog: never let the bot die silently
# --------------------------------------------------------------------------- #

def _supervisor():
    setup_logging()
    log.info("[Telegram Bot] Supervisor started.")
    delay = 5
    while True:
        config = load_config()
        if not config:
            log.info("[Telegram Bot] config.json has no token yet — waiting 30s.")
            time.sleep(30)
            continue
        try:
            bot = ControlBot(config)
            bot.register_commands()
            bot.run_polling()  # returns only if the token changed on disk
            delay = 5
        except Exception:
            with _state_lock:
                _bot_state["restarts"] += 1
                restarts = _bot_state["restarts"]
            log.error(
                "[Telegram Bot] Polling crashed, restarting in %ss (restart #%s):\n%s",
                delay, restarts, traceback.format_exc(),
            )
            time.sleep(delay)
            delay = min(delay * 2, 120)


def _watchdog_check(supervisor_ref):
    """One watchdog pass: restart a dead supervisor thread, warn on stale heartbeat.

    Returns True when a dead supervisor had to be restarted.
    """
    thread = supervisor_ref.get("thread")
    if thread is None or thread.is_alive():
        with _state_lock:
            hb = _bot_state["heartbeat"]
        if hb and time.time() - hb > 600:
            log.error(
                "[Telegram Bot] Watchdog: polling heartbeat is stale (%ss).",
                int(time.time() - hb),
            )
        return False
    log.error("[Telegram Bot] Watchdog: supervisor thread died — starting a new one.")
    with _state_lock:
        _bot_state["restarts"] += 1
    new_thread = threading.Thread(target=_supervisor, name="telegram-controlbot", daemon=True)
    supervisor_ref["thread"] = new_thread
    new_thread.start()
    return True


def _watchdog(supervisor_ref):
    """Keeps watch over the supervisor thread itself; restarts it if it ever dies."""
    while True:
        time.sleep(60)
        try:
            _watchdog_check(supervisor_ref)
        except Exception:
            log.error("[Telegram Bot] Watchdog error:\n%s", traceback.format_exc())


_supervisor_ref = {"thread": None}


def start_bot_daemon():
    thread = threading.Thread(target=_supervisor, name="telegram-controlbot", daemon=True)
    _supervisor_ref["thread"] = thread
    thread.start()
    watchdog = threading.Thread(
        target=_watchdog, args=(_supervisor_ref,), name="telegram-controlbot-watchdog", daemon=True
    )
    watchdog.start()
    return thread
