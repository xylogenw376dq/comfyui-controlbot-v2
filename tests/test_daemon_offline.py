# -*- coding: utf-8 -*-
"""Offline tests for telegram_daemon: monkeypatch TelegramAPI so nothing is really sent."""
import io
import json
import os
import re
import sys
import threading
import time
import types

sys.stdout.reconfigure(encoding="utf-8")
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import telegram_daemon as td

SENT = []
UPLOADED = []
INPUT_FILES = ["example.png", "mask.png"]  # fake ComfyUI input folder listing

class FakeAPI:
    def send_message(self, chat_id, text, parse_mode=None):
        SENT.append(("msg", chat_id, text))
        return len(SENT)

    def edit_message(self, chat_id, message_id, text):
        SENT.append(("edit", chat_id, text))
        return message_id

    def send_photo(self, chat_id, blob, caption="", reply_markup=None):
        SENT.append(("photo", chat_id, len(blob), caption[:40], bool(reply_markup)))
        return 1

    def send_album(self, chat_id, blobs, caption=""):
        SENT.append(("album", chat_id, len(blobs), caption[:40]))
        return True

    def send_video(self, chat_id, video_bytes, caption="", filename="video.mp4"):
        SENT.append(("video", chat_id, len(video_bytes), caption[:40], filename))
        return 1

    def download_file(self, file_id):
        if file_id == "bad":
            return None, td.MsgError("img_dl_failed", {"reason": "getFile"})
        return b"\xff\xd8FAKEJPEG", None

    def _request(self, *a, **k):
        return {}

    def get(self, *a, **k):
        return []

class FakeComfy:
    def get(self, path, timeout=10):
        if path == "/queue":
            return {"queue_running": [], "queue_pending": []}
        if path.startswith("/object_info/"):
            cls = path.split("/")[-1]
            if cls == "KSamplerAdvanced":
                return {"KSamplerAdvanced": {"input": {"required": {
                    "steps": ["INT", {"default": 20, "min": 1, "max": 10000}],
                    "cfg": ["FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0}],
                    "sampler_name": [["euler", "res_multistep", "ddim"]],
                    "scheduler": [["simple", "karras", "beta"]],
                }}}}
            if cls == "EmptySD3LatentImage":
                return {"EmptySD3LatentImage": {"input": {"required": {
                    "width": ["INT", {"default": 1024, "min": 16, "max": 16384}],
                    "height": ["INT", {"default": 1024, "min": 16, "max": 16384}],
                }}}}
            if cls == "CLIPTextEncode":
                return {"CLIPTextEncode": {"input": {"required": {
                    "text": ["STRING", {"multiline": True}],
                }}}}
            if cls == "LoadImage":
                return {"LoadImage": {"input": {"required": {"image": [INPUT_FILES]}}}}
            if cls == "ModelPatchLoader":
                return {"ModelPatchLoader": {"input": {"required": {"name": [[
                    "Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors",
                    "Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors",
                    "Z-Image-Turbo-Fun-Controlnet-Union-2.1-lite-2602-8steps.safetensors",
                ]]}}}}
            if cls == "LoraLoader":
                return {"LoraLoader": {"input": {"required": {
                    "lora_name": [["aesthetic_exp1.safetensors", "MoriimeZ.safetensors"]],
                    "strength_model": ["FLOAT", {"default": 1.0}],
                    "strength_clip": ["FLOAT", {"default": 1.0}],
                    "model": ["MODEL"],
                    "clip": ["CLIP"],
                }}}}
            if cls == "AIO_Preprocessor":
                return {"AIO_Preprocessor": {"input": {"required": {
                    "image": ["IMAGE"],
                    "preprocessor": [["OpenposePreprocessor", "DepthAnythingV2Preprocessor", "CannyEdgePreprocessor", "HEDPreprocessor", "M_LSDPreprocessor"]],
                }}}}
            return {}
        return {}

    def post(self, path, payload=None, timeout=15):
        if path == "/prompt":
            return {"prompt_id": "test-123"}
        return {}

    def fetch_image(self, *a):
        return b"\x89PNG" * 100

    def upload_image(self, blob, filename):
        UPLOADED.append((filename, len(blob)))
        return filename

    def object_info(self, cls, refresh=False):
        return (self.get(f"/object_info/{cls}", timeout=30) or {}).get(cls) or {}

config = dict(td.DEFAULT_CONFIG)
config.update({
    "telegram_token": "TEST", "allowed_users": [1], "admins": [1],
    "workflows": {"txt2img": "workflow_api.json", "img2img": "workflow_img2img_api.json", "video": "workflow_img2video_api.json"},
    "lora_aliases": {
        "amateur": "aesthetic_exp1.safetensors",
        "gothic": "MoriimeZ.safetensors",
        "hands": "Hands v2.1.safetensors",
    },
})

# isolate stores: tests must never touch the production store files
TEMP_DIR = os.environ.get("TEMP", os.path.dirname(os.path.abspath(__file__)))
td.OVERRIDES_PATH = os.path.join(TEMP_DIR, "cb_test_overrides.json")
td.STATE_PATH = os.path.join(TEMP_DIR, "cb_test_state.json")
td.CHAT_SETTINGS_PATH = os.path.join(TEMP_DIR, "cb_test_chat_settings.json")
for _fp in (td.OVERRIDES_PATH, td.STATE_PATH, td.CHAT_SETTINGS_PATH):
    if os.path.exists(_fp):
        os.remove(_fp)

bot = ControlBot = td.ControlBot(config)
bot.api = FakeAPI()
bot.comfy = FakeComfy()

workflow = json.load(open(os.path.join(PLUGIN_DIR, "workflow_api.json"), encoding="utf-8"))
CHAT = 555

def reply_of(n=1):
    out = SENT[-n:]
    return "\n---\n".join(str(s) for s in out)

# --- /help must not raise and must not exceed limits
bot.cmd_help(CHAT, "")
assert any("Генерация" in str(s) for s in SENT), "help text missing"
print("OK /help")

# --- /start
bot.cmd_start(CHAT, "")
print("OK /start")

# --- /nodes lists all node ids
SENT.clear()
bot.cmd_nodes(CHAT, "")
blob = SENT[-1][2]
for nid in ["57:80", "57:13", "81"]:
    assert f"«{nid}»" in blob, f"/nodes missing {nid}"
print("OK /nodes")

# --- /params for a concrete node shows scalar params
SENT.clear()
bot.cmd_params(CHAT, "57:80")
blob = SENT[-1][2]
assert "steps = 8" in blob and "sampler_name = res_multistep" in blob, blob
assert "входы-связи" in blob
print("OK /params node")

# --- /params with ambiguous/missing node
SENT.clear()
bot.cmd_params(CHAT, "nope_node")
assert "не найдена" in SENT[-1][2]
print("OK /params missing")

# --- /set by node.param
SENT.clear()
assert bot.cmd_set(CHAT, "57:80.steps 12") is None
assert "steps: 8 → 12" in SENT[-1][2], SENT[-1][2]
ov = bot.overrides.load()
assert ov["nodes"]["57:80"]["steps"] == 12
print("OK /set node.param")

# --- /set unique param without node
SENT.clear()
bot.cmd_set(CHAT, "shift 5")
ov = bot.overrides.load()
assert ov["nodes"]["57:11"]["shift"] == 5, ov
print("OK /set unique param")

# --- /set param "seed": unique across workflow (node 81) -> direct override
SENT.clear()
bot.cmd_set(CHAT, "seed 123")
assert "81" in SENT[-1][2] and "→ 123" in SENT[-1][2], SENT[-1][2]
print("OK /set unique seed param")

# --- /set with validation: combo unknown value -> options listed
SENT.clear()
bot.cmd_set(CHAT, "sampler_name euler_ancestral")
assert "Допустимые значения" in SENT[-1][2], SENT[-1][2]
print("OK /set combo unknown ->", SENT[-1][2][:80])

# --- /set combo unique partial match canonicalizes
SENT.clear()
bot.cmd_set(CHAT, "sampler_name res_multi")
assert "res_multistep" in SENT[-1][2], SENT[-1][2]
print("OK /set combo partial match")

# --- /set combo exact (case-insensitive)
SENT.clear()
bot.cmd_set(CHAT, "sampler_name RES_MULTISTEP")
assert "res_multistep" in SENT[-1][2], SENT[-1][2]
print("OK /set combo ci match")

# --- /set INT range violation
SENT.clear()
bot.cmd_set(CHAT, "steps 999999")
assert "вне диапазона" in SENT[-1][2], SENT[-1][2]
print("OK /set INT range")

# --- /set wrong type
SENT.clear()
bot.cmd_set(CHAT, "steps abc")
assert "Нужно число (INT)" in SENT[-1][2], SENT[-1][2]
print("OK /set INT type")

# --- /seed random via seed generator node
SENT.clear()
bot.cmd_seed(CHAT, "random")
ov = bot.overrides.load()
assert ov["nodes"]["81"]["mode"] == "random", ov
print("OK /seed random")

# --- /seed fixed
SENT.clear()
bot.cmd_seed(CHAT, "12345")
ov = bot.overrides.load()
assert ov["nodes"]["81"]["mode"] == "fixed" and ov["nodes"]["81"]["seed"] == 12345, ov
print("OK /seed fixed")

# --- /width /height /batch shortcuts
SENT.clear()
bot.cmd_width(CHAT, "1024")
bot.cmd_height(CHAT, "1024")
bot.cmd_batch(CHAT, "2")
ov = bot.overrides.load()
assert ov["nodes"]["57:13"] == {"width": 1024, "height": 1024, "batch_size": 2}, ov["57:13" if "57:13" in ov else "nodes"]
print("OK shortcuts")

# --- apply_overrides: "random" sentinel replaced with int
ov = bot.overrides.load()
ov["nodes"]["81"] = {"mode": "random"}
wf = json.loads(json.dumps(workflow))
bot.apply_overrides(wf, ov)
assert wf["57:13"]["inputs"]["width"] == 1024
assert wf["81"]["inputs"]["mode"] == "random"
assert wf["57:27"]["inputs"]["text"] == "cat"  # prompt override empty
print("OK apply_overrides")

# --- prompt override applied to positive node
ov = bot.overrides.load()
ov["prompt"] = "a dragon"
wf = json.loads(json.dumps(workflow))
bot.apply_overrides(wf, ov)
assert wf["57:27"]["inputs"]["text"] == "a dragon"
print("OK prompt override")

# --- /generate full path: stub the tracker so no background thread interferes
POSTED = []
class PostingComfy(FakeComfy):
    def post(self, path, payload=None, timeout=15):
        if path == "/prompt":
            POSTED.append(payload)
            return {"prompt_id": "test-123"}
        return {}
bot.comfy = PostingComfy()

SENT.clear()
tracker_calls = {}
orig_tracker = bot.track_and_deliver
bot.track_and_deliver = lambda *a, **k: tracker_calls.update(args=a)
bot.cmd_generate(CHAT, "test dragon")
bot.track_and_deliver = orig_tracker

assert tracker_calls, "tracker was not called"
assert tracker_calls["args"][2] == "test dragon", tracker_calls
assert len(POSTED) == 1, POSTED
queued_wf = POSTED[0]["prompt"]
assert queued_wf["57:27"]["inputs"]["text"] == "test dragon"
assert queued_wf["57:13"]["inputs"]["width"] == 1024        # shortcut override applied
assert queued_wf["81"]["inputs"]["mode"] == "fixed"          # /seed fixed applied
assert queued_wf["57:80"]["inputs"]["steps"] == 12           # /set applied
print("OK /generate: workflow queued with prompt + overrides, tracker started")

# --- track_and_deliver with instant history
import types
class HistComfy(FakeComfy):
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {"test-123": {"outputs": {"9": {"images": [
                {"filename": "a.png", "subfolder": "", "type": "output"},
                {"filename": "b.png", "subfolder": "", "type": "output"},
                {"filename": "a.png", "subfolder": "", "type": "output"},  # duplicate
            ]}}}, "status": {"status_str": "success"}}
        return super().get(path, timeout)
bot.comfy = HistComfy()
SENT.clear()
bot.track_and_deliver(CHAT, "test-123", "multi test", {})
kinds = [s[0] for s in SENT]
assert "album" in kinds, SENT  # 2 unique images -> album
album = [s for s in SENT if s[0] == "album"][0]
assert album[2] == 2, album
print("OK track_and_deliver album of 2:", album)

# --- single image -> sendPhoto
class Hist1(HistComfy):
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {"x": {"outputs": {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}, "status": {"status_str": "success"}}}
        return super().get(path, timeout)
bot.comfy = Hist1()
SENT.clear()
bot.track_and_deliver(CHAT, "x", "single", {})
assert any(s[0] == "photo" for s in SENT), SENT
print("OK track_and_deliver single photo")

# --- 11 images -> two albums
class Hist11(HistComfy):
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            imgs = [{"filename": f"i{n}.png", "subfolder": "", "type": "output"} for n in range(11)]
            return {"y": {"outputs": {"9": {"images": imgs}}, "status": {"status_str": "success"}}}
        return super().get(path, timeout)
bot.comfy = Hist11()
SENT.clear()
bot.track_and_deliver(CHAT, "y", "eleven", {})
albums = [s for s in SENT if s[0] == "album"]
assert len(albums) == 2 and albums[0][2] == 10 and albums[1][2] == 1, albums
assert "multi" not in albums[1][3] and "eleven" in albums[0][3], albums  # caption only on first
print("OK 11 images -> 2 albums, caption on first")

# --- error status reported
class HistErr(HistComfy):
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {"e": {"status": {"status_str": "error"}}}
        return super().get(path, timeout)
bot.comfy = HistErr()
SENT.clear()
bot.track_and_deliver(CHAT, "e", "err", {})
assert any("упала" in str(s[2]) for s in SENT if s[0] == "edit"), SENT
print("OK error status")

# --- /unset
SENT.clear()
bot.cmd_unset(CHAT, "57:13.width")
ov = bot.overrides.load()
assert "width" not in ov["nodes"].get("57:13", {}), ov
print("OK /unset")

# --- /reset
bot.cmd_reset(CHAT, "")
assert bot.overrides.load() == {"prompt": None, "nodes": {}}
print("OK /reset")

# --- resolve_target edge: title substring unique
nid, err = td.resolve_target(workflow, "сохранить")
assert nid == "9" and err is None, (nid, err)
nid, err = td.resolve_target(workflow, "ksampler")
assert nid == "57:80", (nid, err)
print("OK resolve_target")

# --- is_wire
assert td.is_wire(["57:80", 0]) and not td.is_wire(["57:80", "x"]) and not td.is_wire([1, 2])
print("OK is_wire")

# --- parse_value
assert td.parse_value("12") == 12 and td.parse_value("1.5") == 1.5
assert td.parse_value("true") is True and td.parse_value("res_multistep") == "res_multistep"
print("OK parse_value")

# --- unknown command handled / access gates
SENT.clear()
bot.handle_text(CHAT, "/definitelynotacmd", "supergroup", None)
assert not SENT, "stranger must be ignored in groups" + str(SENT)
SENT.clear()
bot.handle_text(CHAT, "/definitelynotacmd", "private", None)
assert "Доступ запрещён" in SENT[-1][2], SENT[-1][2]
print("OK deny stranger (silent in group, notice in private)")

SENT.clear()
bot.handle_text(CHAT, "/definitelynotacmd", "private", 1)
assert "Неизвестная команда" in SENT[-1][2], SENT[-1][2]
print("OK unknown command")

# --- /id available to everyone
SENT.clear()
bot.handle_text(CHAT, "/id", "private", None)
assert "Твой ID: None" in SENT[-1][2], SENT[-1][2]
print("OK /id")

# --- command with @botname suffix
SENT.clear()
bot.handle_text(CHAT, "/nodes@my_bot", "private", 1)
assert "Ноды workflow" in SENT[-1][2], SENT[-1][2]
print("OK /cmd@botname")

# --- user management -------------------------------------------------- #
td.CONFIG_PATH = os.path.join(os.environ.get("TEMP", "/tmp"), "controlbot_test_config.json")
with open(td.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"telegram_token": "TEST", "allowed_users": [1], "admins": [1], "comfy_host": "x"}, f)

# admin gate: allowed non-admin cannot manage users
bot.allowed_users.add(999)
SENT.clear()
bot.handle_text(CHAT, "/users", "private", 999)
assert "только для админов" in SENT[-1][2], SENT[-1][2]
print("OK admin gate")

# /users listing for admin
SENT.clear()
bot.handle_text(CHAT, "/users", "private", 1)
blob = SENT[-1][2]
assert "👑 1 (админ)" in blob and "• 999" in blob, blob
print("OK /users")

# /adduser numeric
SENT.clear()
bot.handle_text(CHAT, "/adduser 777", "private", 1)
assert "777 добавлен" in SENT[-1][2], SENT[-1][2]
assert 777 in bot.allowed_users
assert 777 in json.load(open(td.CONFIG_PATH, encoding="utf-8"))["allowed_users"]
print("OK /adduser")

# duplicate add
SENT.clear()
bot.handle_text(CHAT, "/adduser 777", "private", 1)
assert "уже имеет доступ" in SENT[-1][2], SENT[-1][2]
print("OK /adduser duplicate")

# /adduser by reply
SENT.clear()
bot.handle_text(CHAT, "/adduser", "private", 1, 888)
assert "888 добавлен" in SENT[-1][2], SENT[-1][2]
print("OK /adduser by reply")

# bad argument
SENT.clear()
bot.handle_text(CHAT, "/adduser @someuser", "private", 1)
assert "числовой" in SENT[-1][2], SENT[-1][2]
print("OK /adduser bad arg")

# /deluser
SENT.clear()
bot.handle_text(CHAT, "/deluser 777", "private", 1)
assert "777 удалён" in SENT[-1][2], SENT[-1][2]
assert 777 not in bot.allowed_users
print("OK /deluser")

# /deluser of an admin is refused
SENT.clear()
bot.handle_text(CHAT, "/deluser 1", "private", 1)
assert "нельзя удалить" in SENT[-1][2], SENT[-1][2]
print("OK /deluser admin protected")

# /adduser of an admin
SENT.clear()
bot.handle_text(CHAT, "/adduser 1", "private", 1)
assert "админ" in SENT[-1][2], SENT[-1][2]
print("OK /adduser admin target")

os.remove(td.CONFIG_PATH)

# --- review-fix regression tests --------------------------------------- #

# /seed with garbage -> friendly error, no crash
SENT.clear()
bot.cmd_seed(CHAT, "abc")
assert "Нужен номер seed" in SENT[-1][2], SENT[-1][2]
print("OK /seed garbage")

# /seed out of range
SENT.clear()
bot.cmd_seed(CHAT, "-5")
assert "от 0 до" in SENT[-1][2], SENT[-1][2]
print("OK /seed range")

# /seed increment maps to the node mode
SENT.clear()
bot.cmd_seed(CHAT, "increment")
ov = bot.overrides.load()
assert ov["nodes"]["81"]["mode"] == "increment" and "seed" not in ov["nodes"]["81"], ov
print("OK /seed increment")

# NaN must not pass FLOAT validation
SENT.clear()
bot.cmd_set(CHAT, "cfg nan")
assert "конечное число" in SENT[-1][2], SENT[-1][2]
print("OK /set cfg nan rejected")

# bool must not become an INT (int(True) == 1)
SENT.clear()
bot.cmd_set(CHAT, "steps true")
assert "не true/false" in SENT[-1][2], SENT[-1][2]
print("OK /set steps true rejected")

# STRING params coerce numbers to strings
canon, err = bot.validate_value({"class_type": "CLIPTextEncode"}, "text", 123)
assert canon == "123" and err is None, (canon, err)
print("OK STRING coercion")

# node id substring matches: "80" finds "57:80"
nid, err = td.resolve_target(workflow, "80")
assert nid == "57:80" and err is None, (nid, err)
print("OK resolve_target id substring")

# /params shows effective values with override markers
SENT.clear()
bot.cmd_set(CHAT, "steps 12")   # /reset earlier in the file cleared everything
SENT.clear()
bot.cmd_params(CHAT, "57:80")
blob = SENT[-1][2]
assert "steps = 12" in blob and "переопределено" in blob, blob
print("OK /params effective values")

# queue_workflow must never return (None, None)
class NoPidComfy(FakeComfy):
    def post(self, path, payload=None, timeout=15):
        if path == "/prompt":
            return {}
        return {}
bot.comfy = NoPidComfy()
pid, client_id, err = bot.queue_workflow(CHAT, {"1": {"class_type": "X"}})
assert pid is None and err and "prompt_id" in err and client_id, (pid, client_id, err)
print("OK queue_workflow empty response guard")

# progress detail: step + ETA composition
ps = {"value": 4, "max": 8, "done": False}
detail = bot.progress_detail(CHAT, 40, True, False, [], "p", ps)
assert detail == "шаг 4/8 · осталось ~40с", detail  # f=0.5 -> eta == elapsed
ps = {"value": 8, "max": 8, "done": False}
assert bot.progress_detail(CHAT, 40, True, False, [], "p", ps) == "шаг 8/8"
assert bot.progress_detail(CHAT, 40, True, False, [], "p", {"value": 0, "max": 0}) == "выполняется"
assert bot.progress_detail(CHAT, 40, False, True, ["a", "p", "b"], "p", {}) == "в очереди: 2/3"
assert bot.progress_detail(CHAT, 40, False, False, [], "p", {}) == "ждёт"
print("OK progress detail + ETA")

# English variant
bot_lang = td.ControlBot(dict(config, default_language="en"))
bot_lang.api = FakeAPI()
assert bot_lang.progress_detail(CHAT, 40, True, False, [], "p", {"value": 4, "max": 8}) == "step 4/8 · ~40s left"
print("OK progress detail en")

# job vanished from queue and history -> reported, no 30-min hang
class VanishComfy(FakeComfy):
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {}
        if path == "/queue":
            return {"queue_running": [], "queue_pending": []}
        return super().get(path, timeout)
bot.comfy = VanishComfy()
SENT.clear()
bot.track_and_deliver(CHAT, "gone", "vanish test", {})
edits = [s[2] for s in SENT if s[0] == "edit"]
assert any("исчезла из очереди" in e for e in edits), edits
print("OK vanished job detection")

# error with partial results -> still delivered, with warning caption
class PartialErrComfy(FakeComfy):
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {"p1": {"outputs": {"9": {"images": [
                {"filename": "a.png", "subfolder": "", "type": "output"},
            ]}}, "status": {"status_str": "error"}}}
        if path == "/queue":
            return {"queue_running": [], "queue_pending": []}
        return super().get(path, timeout)
bot.comfy = PartialErrComfy()
SENT.clear()
bot.track_and_deliver(CHAT, "p1", "partial test", {})
photos = [s for s in SENT if s[0] == "photo"]
assert photos and "⚠️" in photos[0][3], SENT
assert any("с ошибкой" in str(s[2]) for s in SENT if s[0] == "edit"), SENT
print("OK partial results on error")

# --- self-monitoring --------------------------------------------------- #

# /status includes the bot health line (uptime, restarts, updates)
SENT.clear()
bot.comfy = FakeComfy()
bot.cmd_status(CHAT, "")
blob = SENT[-1][2]
assert "🤖" in blob and "перезапусков полинга" in blob and "аптайм" in blob, blob
print("OK /status bot health line")

# watchdog restarts a dead supervisor thread (with a stubbed supervisor target)
orig_supervisor = td._supervisor
try:
    td._supervisor = lambda: time.sleep(2)  # the restarted thread must not do real polling
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    ref = {"thread": dead}
    before = td._bot_state["restarts"]
    assert td._watchdog_check(ref) is True
    assert ref["thread"] is not dead and ref["thread"].is_alive()
    assert td._bot_state["restarts"] == before + 1
    print("OK watchdog restarts dead supervisor")
finally:
    td._supervisor = orig_supervisor

# alive supervisor + fresh heartbeat -> no restart
live = threading.Thread(target=lambda: time.sleep(2))  # must still be alive during the check
live.start()
with td._state_lock:
    td._bot_state["heartbeat"] = time.time()
ref = {"thread": live}
assert td._watchdog_check(ref) is False
assert td._watchdog_check({"thread": None}) is False  # fresh heartbeat, nothing to do
print("OK watchdog leaves live supervisor alone")

# uptime formatter
assert td.format_uptime(45296) == "12:34:56" or td.format_uptime(45296).endswith("12:34:56")
assert td.format_uptime(90061).startswith("1d")
print("OK format_uptime")

# --- localization ------------------------------------------------------ #

CHAT2 = 555001

# /lang with no args shows the current language
SENT.clear()
bot.cmd_lang(CHAT2, "", "private", 1)
assert "Язык этого чата" in SENT[-1][2] and "ru" in SENT[-1][2], SENT[-1][2]
print("OK /lang status")

# switch to English: replies follow
SENT.clear()
bot.cmd_lang(CHAT2, "en", "private", 1)
assert "English" in SENT[-1][2], SENT[-1][2]
SENT.clear()
bot.cmd_start(CHAT2, "")
assert "Hi! I'm your ComfyUI bot." in SENT[-1][2], SENT[-1][2]
print("OK /lang en switches messages")

# persisted to disk and survives a bot re-creation
settings = json.load(open(td.CHAT_SETTINGS_PATH, encoding="utf-8"))
assert settings["chats"][str(CHAT2)] == "en", settings
bot2 = td.ControlBot(config)
bot2.api = FakeAPI()
bot2.comfy = FakeComfy()
assert bot2.get_lang(CHAT2) == "en", bot2.get_lang(CHAT2)
assert bot2.get_lang(999999) == "ru"  # unknown chat -> default
print("OK /lang persisted across restart")

# unknown language code (chat is English at this point)
SENT.clear()
bot2.cmd_lang(CHAT2, "de", "private", 1)
assert "I don't know" in SENT[-1][2], SENT[-1][2]
print("OK /lang unknown")

# back to Russian
SENT.clear()
bot2.cmd_lang(CHAT2, "ru", "private", 1)
SENT.clear()
bot2.cmd_start(CHAT2, "")
assert "Привет!" in SENT[-1][2], SENT[-1][2]
print("OK /lang back to ru")

# in groups only admins may change the language
SENT.clear()
bot2.cmd_lang(CHAT2, "en", "supergroup", 999)
assert "только админы" in SENT[-1][2], SENT[-1][2]
SENT.clear()
bot2.cmd_lang(CHAT2, "en", "supergroup", 1)
assert "English" in SENT[-1][2], SENT[-1][2]
bot2.cmd_lang(CHAT2, "ru", "supergroup", 1)  # restore
print("OK /lang group admin gate")

# auto-detection from Telegram client language_code
bot2._lang_cache.clear()
bot2.ensure_chat_lang(555002, "en-US")
assert bot2.get_lang(555002) == "en"
bot2.ensure_chat_lang(555003, "fr-FR")  # unsupported -> default, nothing stored
assert bot2.get_lang(555003) == "ru"
assert str(555003) not in json.load(open(td.CHAT_SETTINGS_PATH, encoding="utf-8"))["chats"]
print("OK language auto-detect")

# per-chat command menus registered for localized chats
assert bot2.register_chat_menus() is True
print("OK per-chat menus registered")

# language auto-detect must not fire in groups (language belongs to the chat, set by admins)
GROUP = -100999
bot2._lang_cache.clear()
bot2.ensure_chat_lang(GROUP, "en-US", chat_type="supergroup")
assert bot2.get_lang(GROUP) == "ru"
assert str(GROUP) not in json.load(open(td.CHAT_SETTINGS_PATH, encoding="utf-8"))["chats"]
bot2.ensure_chat_lang(555004, "en-US", chat_type="private")
assert bot2.get_lang(555004) == "en"
print("OK auto-detect private-only")

# --- websocket progress listener ---------------------------------------- #

def _install_fake_ws(script):
    """Inject a fake websocket module whose sockets replay `script`.

    _listen_progress() instantiates its own socket, so the script must be
    passed to the constructor, not poked into a separate instance.
    """
    mod = types.ModuleType("websocket")

    class FakeTimeout(Exception):
        pass

    class FakeSocket:
        def __init__(self):
            self.script = list(script)
            self.closed = False
        def settimeout(self, t): pass
        def connect(self, url, timeout=None): self.url = url
        def recv(self):
            if not self.script:
                raise FakeTimeout()
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        def close(self): self.closed = True

    mod.WebSocketTimeoutException = FakeTimeout
    mod.WebSocket = FakeSocket
    orig = sys.modules.get("websocket")
    sys.modules["websocket"] = mod
    return orig

bot.comfy = FakeComfy()
bot.comfy.host = "127.0.0.1:8188"

# normal flow: binary skipped, foreign prompt filtered, ours captured, done on executing-None
orig_mod = _install_fake_ws([
    b"\x00\x01binary-frame",
    "not json at all",
    json.dumps({"type": "progress", "data": {"prompt_id": "other", "value": 9, "max": 9}}),
    json.dumps({"type": "progress", "data": {"prompt_id": "p1", "value": 3, "max": 8}}),
    json.dumps({"type": "executing", "data": {"prompt_id": "p1", "node": None}}),
])
try:
    ps = {"value": 0, "max": 0, "done": False}
    bot._listen_progress("p1", "cid", ps)
    assert ps["done"] is True and ps["value"] == 3 and ps["max"] == 8, ps
    print("OK ws listener parses and filters events")

    # fatal recv error -> loop breaks immediately instead of spinning
    class Boom(Exception):
        pass
    _install_fake_ws([Boom("connection reset"), Boom("connection reset"), Boom("connection reset")])
    ps = {"value": 0, "max": 0, "done": False}
    bot._listen_progress("p1", "cid", ps)
    assert ps["done"] is True
    print("OK ws listener exits on fatal recv error")
finally:
    if orig_mod is None:
        sys.modules.pop("websocket", None)
    else:
        sys.modules["websocket"] = orig_mod

# --- i18n coverage: every key used in code must exist in every language -- #

src = open(os.path.join(PLUGIN_DIR, "telegram_daemon.py"), encoding="utf-8").read()
used = set(re.findall(r"\.t\(\s*chat_id,\s*[\"']([a-z_]+)[\"']", src, re.S))
used |= set(re.findall(r"MsgError\(\s*[\"']([a-z_]+)[\"']", src))
used |= {"seed_random", "seed_increment", "seed_decrement"}  # f"seed_{mode}" is dynamic
for lang in ("ru", "en"):
    missing = used - set(td.STRINGS[lang])
    assert not missing, f"missing keys in {lang}: {missing}"
print(f"OK i18n coverage: {len(used)} keys present in ru+en")

# --- img2img: media handling and workflow switching ---------------------- #

# extract_image_ref: photo / image document / non-image document / nothing
PHOTO_MSG = {"photo": [
    {"file_id": "small", "width": 320, "height": 240},
    {"file_id": "big", "width": 1280, "height": 960},
]}
assert bot.extract_image_ref(PHOTO_MSG) == {"file_id": "big", "ext": "jpg"}
assert bot.extract_image_ref({"document": {"mime_type": "image/png", "file_id": "d1", "file_name": "a.PNG"}}) == {"file_id": "d1", "ext": "PNG"}
assert bot.extract_image_ref({"document": {"mime_type": "video/mp4", "file_id": "v1"}}) is None
assert bot.extract_image_ref({}) is None
assert bot.extract_image_ref(None) is None
print("OK extract_image_ref")

# find_load_image_node
assert td.find_load_image_node({"50": {"class_type": "LoadImage", "inputs": {"image": "x"}}}) == "50"
assert td.find_load_image_node({"27": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}}) is None
print("OK find_load_image_node")

# per-chat workflow selection with persistence and unknown fallback
assert bot.get_chat_workflow(CHAT) == "txt2img"
bot.set_chat_workflow(CHAT, "img2img")
assert bot.get_chat_workflow(CHAT) == "img2img"
stored = json.load(open(td.CHAT_SETTINGS_PATH, encoding="utf-8"))
assert stored["workflows"][str(CHAT)] == "img2img"
bot2b = td.ControlBot(config)
bot2b.api = FakeAPI()
assert bot2b.get_chat_workflow(CHAT) == "img2img"  # survives restart
assert bot2b.get_chat_workflow(123456) == "txt2img"  # untouched chat -> default
bot2b.chat_settings.mutate(lambda s: s["workflows"].update({str(CHAT): "nope"}))
assert bot2b.get_chat_workflow(CHAT) == "txt2img"  # unknown name -> default
print("OK per-chat workflow selection")

# /workflow command: status, switch, unknown
SENT.clear()
bot2b.cmd_workflow(CHAT, "", "private", 1)
assert "txt2img" in SENT[-1][2] and "img2img" in SENT[-1][2]
SENT.clear()
bot2b.cmd_workflow(CHAT, "img2img", "private", 1)
assert "img2img" in SENT[-1][2] and bot2b.get_chat_workflow(CHAT) == "img2img"
SENT.clear()
bot2b.cmd_workflow(CHAT, "video2video", "private", 1)
assert "Не знаю workflow" in SENT[-1][2]
print("OK /workflow command")

# /generate with img2img active but no image -> asks for the image
bot2b.set_chat_workflow(CHAT, "img2img")
bot2b.comfy = FakeComfy()
SENT.clear()
bot2b.cmd_generate(CHAT, "make it cyberpunk")
assert any("картинку" in str(s[2]) for s in SENT), SENT
print("OK img2img without image -> hint")

# /generate with image: uploaded and wired into LoadImage
UPLOADED.clear()
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.comfy.upload_image = lambda blob, filename: (UPLOADED.append((filename, len(blob))) or filename)
bot2b.cmd_generate(CHAT, "make it cyberpunk", {"file_id": "good", "ext": "jpg"})
assert len(POSTED) == 1, POSTED
img_node = td.find_load_image_node(POSTED[0]["prompt"])
assert img_node and POSTED[0]["prompt"][img_node]["inputs"]["image"].startswith("tg_"), POSTED[0]["prompt"][img_node]
assert POSTED[0]["prompt"][img_node]["inputs"]["image"].endswith(".jpg")
assert len(UPLOADED) == 1
print("OK img2img with image: uploaded + injected")

# /generate with image while txt2img active -> warning, queued without image
bot2b.set_chat_workflow(CHAT, "txt2img")
UPLOADED.clear()
POSTED.clear()
bot2b.comfy = PostingComfy()
SENT.clear()
bot2b.cmd_generate(CHAT, "plain text2img", {"file_id": "good", "ext": "jpg"})
assert any("не использует" in str(s[2]) for s in SENT), SENT
assert len(POSTED) == 1
print("OK image with txt2img -> warning")

# download failure -> friendly error, nothing queued
bot2b.set_chat_workflow(CHAT, "img2img")
POSTED.clear()
SENT.clear()
bot2b.cmd_generate(CHAT, "cyberpunk", {"file_id": "bad", "ext": "jpg"})
assert any("скачать" in str(s[2]) for s in SENT), SENT
assert not POSTED
print("OK image download failure handled")

# --- ControlNet --------------------------------------------------------- #

# patch pick heuristics: full Union-2.1 preferred over 8steps/lite
patch, err = bot2b.pick_patch_name(bot2b.get_cnet_settings(CHAT))
assert patch == "Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors" and err is None, (patch, err)
print("OK pick_patch_name heuristics")

# /cnet command: status -> on -> mode -> strength -> photo -> clear
SENT.clear()
bot2b.cmd_cnet(CHAT, "", "private", 1)
assert "выкл" in SENT[-1][2], SENT[-1][2]
SENT.clear()
bot2b.cmd_cnet(CHAT, "on", "private", 1)
assert "включён" in SENT[-1][2] and "не найдена" not in SENT[-1][2], SENT[-1][2]
assert bot2b.get_cnet_settings(CHAT)["enabled"] is True
SENT.clear()
bot2b.cmd_cnet(CHAT, "mode depth", "private", 1)
assert bot2b.get_cnet_settings(CHAT)["prep"] == "DepthAnythingV2Preprocessor", bot2b.get_cnet_settings(CHAT)
SENT.clear()
bot2b.cmd_cnet(CHAT, "mode list", "private", 1)
assert "DepthAnythingV2Preprocessor" in SENT[-1][2], SENT[-1][2]  # 'list' shows the menu, not an error
print("OK /cnet mode list")
SENT.clear()
bot2b.cmd_cnet(CHAT, "mode bones", "private", 1)  # partial match -> Openpose
assert bot2b.get_cnet_settings(CHAT)["prep"] == "OpenposePreprocessor"
SENT.clear()
bot2b.cmd_cnet(CHAT, "strength 0.65", "private", 1)
assert bot2b.get_cnet_settings(CHAT)["strength"] == 0.65
SENT.clear()
bot2b.cmd_cnet(CHAT, "", "private", 1)
assert "вкл" in SENT[-1][2] and "OpenposePreprocessor" in SENT[-1][2], SENT[-1][2]
print("OK /cnet command and settings")

# group: non-admin cannot change cnet
SENT.clear()
bot2b.cmd_cnet(CHAT, "off", "supergroup", 999)
assert "только админы" in SENT[-1][2], SENT[-1][2]
bot2b.cmd_cnet(CHAT, "on", "private", 1)
print("OK /cnet group admin gate")

# mask pipeline: reference photo -> preprocessed preview -> pending approval
class MaskComfy(FakeComfy):
    """FakeComfy that completes the mask workflow instantly with one output image."""
    def post(self, path, payload=None, timeout=15):
        if path == "/prompt":
            POSTED.append(payload)
            return {"prompt_id": "maskjob", "client_id": "c"}
        return {}
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {"maskjob": {"outputs": {"__mask_save": {"images": [
                {"filename": "cnet_mask_1.png", "subfolder": "", "type": "output"},
            ]}}}, "status": {"status_str": "success"}}
        return super().get(path, timeout)
bot2b.comfy = MaskComfy()
SENT.clear()
bot2b.api.download_file = lambda file_id: (b"REFBYTES", None)
bot2b.cmd_cnet(CHAT, "", "private", 1, {"file_id": "ref", "ext": "png"})
photos = [s for s in SENT if s[0] == "photo"]
assert photos, SENT
assert "Маска готова" in photos[0][3], photos[0][3]
assert bot2b._pending_masks[str(CHAT)]["images"][0]["filename"] == "cnet_mask_1.png"
print("OK mask preview prepared with keyboard")

# approve: mask uploaded to input and stored
UPLOADED.clear()
assert bot2b._approve_mask(CHAT) is None
st = bot2b.get_cnet_settings(CHAT)
assert st["mask_name"].startswith("tg_cnetmask_"), st
INPUT_FILES.append(st["mask_name"])  # the upload appears in the input folder listing
assert len(UPLOADED) == 1
# second approve without pending -> error
assert bot2b._approve_mask(CHAT) is not None
print("OK mask approval stores the mask")

# generation with cnet enabled + mask: injected graph (img2img, with preprocessor)
POSTED.clear()
UPLOADED.clear()
bot2b.comfy = PostingComfy()
bot2b.comfy.upload_image = lambda blob, filename: (UPLOADED.append(filename) or filename)
bot2b.cmd_generate(CHAT, "cyberpunk city", {"file_id": "good", "ext": "jpg"})
assert len(POSTED) == 1, POSTED
q = POSTED[0]["prompt"]
assert "__cnet_patch" in q and "__cnet_img" in q and "__cnet_apply" in q and "__cnet_prep" in q
assert q["__cnet_apply"]["inputs"]["model"] == ["11", 0], q["__cnet_apply"]
assert q["__cnet_apply"]["inputs"]["vae"] == ["29", 0]
assert q["__cnet_apply"]["inputs"]["strength"] == 0.65
assert q["80"]["inputs"]["model"] == ["__cnet_apply", 0]
assert q["__cnet_apply"]["inputs"]["image"] == ["__cnet_prep", 0]
assert q["__cnet_prep"]["inputs"]["preprocessor"] == "OpenposePreprocessor"
assert q["__cnet_img"]["inputs"]["image"] == st["mask_name"]  # the approved mask
assert len(UPLOADED) == 1  # only the main image; the mask is already in input
print("OK cnet injection (with preprocessor)")

# txt2img + cnet: VAELoader fallback for the vae wire
bot2b.set_chat_workflow(CHAT, "txt2img")
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "a cyberpunk city")
q = POSTED[0]["prompt"]
assert "__cnet_apply" in q
assert q["57:80"]["inputs"]["model"] == ["__cnet_apply", 0]
assert q["__cnet_apply"]["inputs"]["vae"] == ["57:29", 0]  # from VAELoader
assert q["__cnet_img"]["inputs"]["image"] == st["mask_name"]
print("OK cnet injection into txt2img (VAELoader fallback)")

# cnet enabled but no mask -> error, nothing queued
bot2b.set_cnet_settings(CHAT, mask_name=None)
POSTED.clear()
SENT.clear()
bot2b.cmd_generate(CHAT, "a cyberpunk city")
assert any("маска не задана" in str(s[2]) for s in SENT), SENT
assert not POSTED
print("OK cnet without mask -> hint")

# cnet disabled -> no cnet nodes
bot2b.set_cnet_settings(CHAT, enabled=False, mask_name="mask.png")
bot2b.set_chat_workflow(CHAT, "img2img")
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "cyberpunk city", {"file_id": "good", "ext": "jpg"})
q = POSTED[0]["prompt"]
assert "__cnet_apply" not in q and q["80"]["inputs"]["model"] == ["11", 0]
print("OK cnet disabled -> clean graph")

# mask lost from input folder -> error
bot2b.set_cnet_settings(CHAT, enabled=True, mask_name="gone.png")
POSTED.clear()
SENT.clear()
bot2b.cmd_generate(CHAT, "cyberpunk", {"file_id": "good", "ext": "jpg"})
assert any("недоступна" in str(s[2]) for s in SENT), SENT
assert not POSTED
print("OK lost mask detected")

# stale object_info cache must not hide a freshly approved mask
class CountingComfy(PostingComfy):
    """Server that always serves a listing WITH the new mask; counts refreshes."""
    def __init__(self):
        self.fetches = 0
        self._object_info = {"LoadImage": {"input": {"required": {"image": [["example.png"]]}}}}  # stale cache
    def object_info(self, cls, refresh=False):
        if refresh or cls not in self._object_info or not self._object_info[cls]:
            self.fetches += 1
            if cls == "LoadImage":
                self._object_info[cls] = {"input": {"required": {"image": [INPUT_FILES + ["new_mask.png"]]}}}
            elif cls == "ModelPatchLoader":
                self._object_info[cls] = {"input": {"required": {"name": [[
                    "Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors"]]}}}
            else:
                self._object_info[cls] = {}
        return self._object_info[cls]
bot2b.comfy = CountingComfy()
bot2b.set_cnet_settings(CHAT, enabled=True, mask_name="new_mask.png", prep="")
POSTED.clear()
bot2b.cmd_generate(CHAT, "cyberpunk", {"file_id": "good", "ext": "jpg"})
assert len(POSTED) == 1 and "__cnet_apply" in POSTED[0]["prompt"], POSTED
assert bot2b.comfy.fetches >= 1  # refresh forced a refetch despite the stale cache
bot2b.set_cnet_settings(CHAT, enabled=False)
print("OK object_info refresh picks up new mask")

# unknown prep -> error, nothing queued
bot2b.set_cnet_settings(CHAT, enabled=True, prep="BoneSawPreprocessor", mask_name="mask.png")
POSTED.clear()
SENT.clear()
bot2b.cmd_generate(CHAT, "cyberpunk", {"file_id": "good", "ext": "jpg"})
assert any("не найден" in str(s[2]) for s in SENT), SENT
assert not POSTED
bot2b.set_cnet_settings(CHAT, enabled=False, prep="")
print("OK unknown preprocessor rejected")

# --- img2img: batch and denoise ----------------------------------------- #

bot2b.set_chat_workflow(CHAT, "img2img")
SENT.clear()
bot2b.cmd_batch(CHAT, "2")
ov = bot2b.overrides.load()
assert ov["nodes"]["52"]["amount"] == 2, ov  # RepeatLatentBatch amount
SENT.clear()
bot2b.cmd_denoise(CHAT, "0.8")
ov = bot2b.overrides.load()
assert ov["nodes"]["80"]["denoise"] == 0.8, ov
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "cyberpunk", {"file_id": "good", "ext": "jpg"})
q = POSTED[0]["prompt"]
assert q["52"]["inputs"]["amount"] == 2 and q["80"]["inputs"]["denoise"] == 0.8, (q["52"], q["80"])
assert q["80"]["inputs"]["latent_image"] == ["52", 0]
print("OK img2img batch + denoise")

# --- LoRA ---------------------------------------------------------------- #

bot2b.set_chat_workflow(CHAT, "txt2img")
bot2b.comfy = PostingComfy()  # FakeComfy.object_info knows LoraLoader
SENT.clear()
bot2b.cmd_lora(CHAT, "", "private", 1)
assert "нет" in SENT[-1][2], SENT[-1][2]
SENT.clear()
bot2b.cmd_lora(CHAT, "amateur", "private", 1)
assert "amateur" in SENT[-1][2], SENT[-1][2]
assert bot2b.get_lora_settings(CHAT)["alias"] == "amateur"
SENT.clear()
bot2b.cmd_lora(CHAT, "strength 0.5", "private", 1)
assert bot2b.get_lora_settings(CHAT)["strength"] == 0.5
SENT.clear()
bot2b.cmd_lora(CHAT, "gothic", "private", 1)  # switch to another lora
assert bot2b.get_lora_settings(CHAT)["alias"] == "gothic"
SENT.clear()
bot2b.cmd_lora(CHAT, "list", "private", 1)
blob = SENT[-1][2]
assert "gothic" in blob and "👈 выбрана" in blob and "❌ hands" in blob, blob  # hands file not in combo
SENT.clear()
bot2b.cmd_lora(CHAT, "hands", "private", 1)
assert "отсутствует" in SENT[-1][2], SENT[-1][2]
print("OK /lora command and settings")

# group: non-admin gate
SENT.clear()
bot2b.cmd_lora(CHAT, "off", "supergroup", 999)
assert "только админы" in SENT[-1][2], SENT[-1][2]
print("OK /lora group admin gate")

# generation with lora: model + clip wired through LoraLoader
bot2b.set_cnet_settings(CHAT, enabled=False, mask_name=None)
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "a cyberpunk city")
assert len(POSTED) == 1, POSTED
q = POSTED[0]["prompt"]
assert "__lora" in q
assert q["__lora"]["inputs"]["lora_name"] == "MoriimeZ.safetensors"
assert q["__lora"]["inputs"]["strength_model"] == 0.5 and q["__lora"]["inputs"]["strength_clip"] == 0.5
assert q["__lora"]["inputs"]["model"] == ["57:11", 0] and q["__lora"]["inputs"]["clip"] == ["57:30", 0]
assert q["57:80"]["inputs"]["model"] == ["__lora", 0]
assert q["57:27"]["inputs"]["clip"] == ["__lora", 1]
print("OK lora injection (txt2img)")

# lora + controlnet chain: base -> lora -> controlnet -> sampler
bot2b.set_cnet_settings(CHAT, enabled=True, mask_name="mask.png", strength=0.9)
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "a cyberpunk city")
q = POSTED[0]["prompt"]
assert q["57:80"]["inputs"]["model"] == ["__cnet_apply", 0]
assert q["__cnet_apply"]["inputs"]["model"] == ["__lora", 0]
assert q["__lora"]["inputs"]["model"] == ["57:11", 0]
assert q["__cnet_apply"]["inputs"]["strength"] == 0.9
print("OK lora + controlnet chain order")

# lora off -> clean graph
bot2b.set_lora_settings(CHAT, alias=None)
bot2b.set_cnet_settings(CHAT, enabled=False, mask_name=None)
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "a cyberpunk city")
q = POSTED[0]["prompt"]
assert "__lora" not in q and q["57:80"]["inputs"]["model"] == ["57:11", 0]
assert q["57:27"]["inputs"]["clip"] == ["57:30", 0]
print("OK lora off -> clean graph")

# --- video delivery ------------------------------------------------------ #

class VideoHistoryComfy(PostingComfy):
    """History entry with an .mp4 under the regular images key (SaveVideo format)."""
    def get(self, path, timeout=10):
        if path.startswith("/history/"):
            return {"v1": {"outputs": {"9": {"images": [
                {"filename": "wan22-video_00001_.mp4", "subfolder": "video", "type": "output"},
            ]}}}, "status": {"status_str": "success"}}
        return super().get(path, timeout)

bot2b.set_chat_workflow(CHAT, "img2img")
bot2b.set_lora_settings(CHAT, alias=None)
bot2b.set_cnet_settings(CHAT, enabled=False, mask_name=None)
bot2b.comfy = VideoHistoryComfy()
SENT.clear()
bot2b.track_and_deliver(CHAT, "v1", "video test", {})
vids = [s for s in SENT if s[0] == "video"]
assert vids and vids[0][4].endswith(".mp4"), SENT
assert not [s for s in SENT if s[0] == "photo"], SENT
print("OK video delivery via sendVideo")

# --- video workflow: TI2V text-only mode and cnet guard ------------------ #

bot2b.set_chat_workflow(CHAT, "video")
bot2b.comfy = PostingComfy()

# text-only /generate on the video workflow: no img_need, start_image dropped
SENT.clear()
POSTED.clear()
bot2b.cmd_generate(CHAT, "a cabin in the mountains, clouds drifting")
assert len(POSTED) == 1, POSTED
q = POSTED[0]["prompt"]
assert "50" not in q, "LoadImage should be dropped in T2V mode"
lv = next(n for n in q.values() if n.get("class_type") == "Wan22ImageToVideoLatent")
assert "start_image" not in lv["inputs"], lv
assert q["27"]["inputs"]["text"] == "a cabin in the mountains, clouds drifting"
print("OK video T2V mode (text-only)")

# with a photo -> I2V mode keeps start_image wired
POSTED.clear()
bot2b.cmd_generate(CHAT, "clouds drifting", {"file_id": "good", "ext": "jpg"})
q = POSTED[0]["prompt"]
lv = next(n for n in q.values() if n.get("class_type") == "Wan22ImageToVideoLatent")
assert "start_image" in lv["inputs"], lv
print("OK video I2V mode (photo kept)")

# cnet enabled on video workflow -> skipped with a notice, graph untouched
bot2b.set_cnet_settings(CHAT, enabled=True, mask_name="mask.png", prep="")
POSTED.clear()
SENT.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "clouds drifting")
q = POSTED[0]["prompt"]
assert "__cnet_apply" not in q, "cnet must not patch the Wan model"
assert any("не применяется к video" in str(s[2]) for s in SENT), SENT
bot2b.set_cnet_settings(CHAT, enabled=False)
print("OK cnet skipped on video workflow")

# --- prompting tips per workflow ----------------------------------------- #

bot2b.set_chat_workflow(CHAT, "txt2img")
SENT.clear()
bot2b.cmd_tips(CHAT, "")
assert "Z-Image Turbo" in SENT[-1][2], SENT[-1][2]
bot2b.set_chat_workflow(CHAT, "video")
SENT.clear()
bot2b.cmd_tips(CHAT, "")
assert "Wan 2.2 TI2V 5B" in SENT[-1][2] and "ДВИЖЕНИЕ" in SENT[-1][2], SENT[-1][2]
print("OK /tips per workflow")

# real download_file: retries transient failures, respects 429, reports final status
class FakeResp:
    def __init__(self, status, body=b""):
        self.status_code = status
        self.text = body
        self.content = b"FILEBYTES"
    def json(self):
        return {"parameters": {"retry_after": 0}}

class FlakySession:
    """Fails twice, then succeeds; also serves the all-fail scenario."""
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0
    def get(self, url, timeout=None):
        self.calls += 1
        s = self.statuses.pop(0) if self.statuses else 200
        return FakeResp(s)

orig_sleep = td.time.sleep
td.time.sleep = lambda s: None  # keep the test fast
try:
    api = td.TelegramAPI("TESTTOKEN")
    api._request = lambda method, data=None, files=None, timeout=None: {
        "file_path": "photos/f.jpg", "file_size": 103000
    }
    api.session = FlakySession([502, 429, 200])
    blob, err = api.download_file("x")
    assert blob == b"FILEBYTES" and err is None, (blob, err)
    assert api.session.calls == 3
    print("OK download_file retries to success")

    api2 = td.TelegramAPI("TESTTOKEN")
    api2._request = api._request
    api2.session = FlakySession([502, 500, 502])
    blob, err = api2.download_file("x")
    assert blob is None and err.key == "img_dl_failed" and err.kw["reason"] == "HTTP 502", err
    print("OK download_file all-fail -> reason reported")

    api3 = td.TelegramAPI("TESTTOKEN")
    api3._request = lambda method, data=None, files=None, timeout=None: {
        "file_path": "photos/f.jpg", "file_size": 25_000_000
    }
    blob, err = api3.download_file("x")
    assert blob is None and err.key == "img_too_large", err
    print("OK download_file size limit")
finally:
    td.time.sleep = orig_sleep

# --- cleanup: remove test store files
for fp in (td.OVERRIDES_PATH, td.STATE_PATH, td.CHAT_SETTINGS_PATH):
    if os.path.exists(fp):
        os.remove(fp)

print("\nALL TESTS PASSED")
