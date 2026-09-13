# -*- coding: utf-8 -*-
"""One-off patch: chained img2video (seconds -> segments -> last-frame chaining -> assembly)."""
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================ telegram_daemon.py ============================
p = "telegram_daemon.py"
src = open(p, encoding="utf-8").read()

# --- 1) module helpers after chunks() ---
old = """def chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]"""
new = old + """


def nearest_4n1(frames):
    \"\"\"Closest valid Wan latent length: 4n+1 (min 5).\"\"\"
    n = max(1, int(round((int(frames) - 1) / 4)))
    return 4 * n + 1


def plan_video_segments(total_frames, cap=81):
    \"\"\"Split a frame budget into Wan segments of <= cap frames (each 4n+1).\"\"\"
    if total_frames <= cap:
        return [nearest_4n1(total_frames)]
    cycles = -(-total_frames // cap)
    last = total_frames - (cycles - 1) * cap
    return [cap] * (cycles - 1) + [nearest_4n1(max(last, 5))]


def video_last_frame_png(mp4_bytes):
    \"\"\"Decode the last frame of an mp4 (bytes) -> PNG bytes, or None.\"\"\"
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
    \"\"\"Concatenate segment mp4s: drop the first frame of segments 2+, re-encode h264.\"\"\"
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
    return buf.getvalue()"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

# --- 2) settings accessors after set_lora_settings ---
old = """    def set_lora_settings(self, chat_id, **kw):
        self.chat_settings.mutate(
            lambda s: s.setdefault("lora", {}).setdefault(str(chat_id), {}).update(kw)
        )"""
new = old + """

    def get_video_settings(self, chat_id):
        defaults = {"seconds": 2}
        stored = (self.chat_settings.load().get("video") or {}).get(str(chat_id)) or {}
        out = dict(defaults)
        out.update({k: v for k, v in stored.items() if v is not None})
        return out

    def set_video_settings(self, chat_id, **kw):
        self.chat_settings.mutate(
            lambda s: s.setdefault("video", {}).setdefault(str(chat_id), {}).update(kw)
        )"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

# --- 3) cmd_vseconds after cmd_lora (anchor: end of cmd_lora) ---
old = """        self.set_lora_settings(chat_id, alias=match_alias)
        log.info("LoRA for chat %s set to %s", chat_id, match_alias)
        self.api.send_message(
            chat_id, self.t(chat_id, "lora_set", name=match_alias, strength=st["strength"])
        )"""
new = old + """

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
        ))"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

# --- 4) dispatch ---
old = """            elif cmd == "lora":
                handler(chat_id, arg, chat_type, user_id)"""
new = old + """
            elif cmd == "vseconds":
                handler(chat_id, arg, chat_type, user_id)"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

# --- 5) video branch in cmd_generate: plan + chain thread before queue ---
old = """            log.info("ControlNet injected for chat %s", chat_id)

        prompt_id, client_id, err = self.queue_workflow(chat_id, workflow)"""
new = """        # video workflow: split the duration into <=81-frame segments and chain them
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

        prompt_id, client_id, err = self.queue_workflow(chat_id, workflow)"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

# --- 6) the chained runner after track_and_deliver (anchor: deliver_media def) ---
old = "    def deliver_media(self, chat_id, media, caption):"
new = '''    def run_video_chain(self, chat_id, base_workflow, plan, first_image_name, seconds, prompt_text):
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

    def deliver_media(self, chat_id, media, caption):'''
assert src.count(old) == 1
src = src.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(src)
print("telegram_daemon patched")

# ============================ bot_strings.py ============================
p2 = "bot_strings.py"
s = open(p2, encoding="utf-8").read()
NL = chr(92) + "n"

anchor_ru = '"cnet_video_skip": "ℹ️ ControlNet не применяется к video-workflow — генерирую без него.",'
add_ru = anchor_ru + '''
        "vseconds_status": "🎥 Видео: {seconds} с → {frames} кадров → {segments} сегм. (по ≤81 кадра). Изменить: /vseconds <сек>",
        "vseconds_set": "🎥 Длительность видео: {seconds} с ({frames} кадров, {segments} сегм. по ≤81 кадра).",
        "vseconds_bad": "Нужно целое число секунд. Пример: /vseconds 6",
        "vseconds_range": "Длительность — от 1 до 30 секунд.",
        "video_segment_progress": "🎥 Видео {seconds}с · сегмент {i}/{n} · {elapsed}с",
        "video_chain_failed": "⚠️ Сегмент {i}/{n} не сгенерировался: {reason}. Попробуй ещё раз или уменьши /vseconds.",
        "video_assembling": "🎞 Склеиваю сегменты…",'''
assert s.count(anchor_ru) == 1
s = s.replace(anchor_ru, add_ru, 1)

anchor_en = '"cnet_video_skip": "ℹ️ ControlNet is not applied to video workflows — generating without it.",'
add_en = anchor_en + '''
        "vseconds_status": "🎥 Video: {seconds} s → {frames} frames → {segments} segments (≤81 frames each). Change: /vseconds <sec>",
        "vseconds_set": "🎥 Video duration: {seconds} s ({frames} frames, {segments} segments of ≤81 frames).",
        "vseconds_bad": "Expected an integer number of seconds. Example: /vseconds 6",
        "vseconds_range": "Duration must be between 1 and 30 seconds.",
        "video_segment_progress": "🎥 Video {seconds}s · segment {i}/{n} · {elapsed}s",
        "video_chain_failed": "⚠️ Segment {i}/{n} failed: {reason}. Try again or lower /vseconds.",
        "video_assembling": "🎞 Assembling segments…",'''
assert s.count(anchor_en) == 1
s = s.replace(anchor_en, add_en, 1)

# menu: tips + vseconds (tips entry not present yet — add both after lora)
lora_menu = '    ("lora", {"ru": "🧩 LoRA: /lora list|имя|off", "en": "🧩 LoRA: /lora list|name|off"}),'
lora_menu_new = lora_menu + '''
    ("tips", {"ru": "💡 Подсказки по промптам", "en": "💡 Prompting tips"}),
    ("vseconds", {"ru": "🎥 Длительность видео: /vseconds 6", "en": "🎥 Video duration: /vseconds 6"}),'''
assert s.count(lora_menu) == 1
s = s.replace(lora_menu, lora_menu_new, 1)

# help: tips + vseconds lines (ru/en)
lora_help_ru = '"/lora — LoRA для обоих флоу: list|имя|strength|off' + NL + '"'
lora_help_ru_new = '"/lora — LoRA для обоих флоу: list|имя|strength|off' + NL + '"' + ' + ' + '"' + NL + '"/tips — как писать промпты для текущего флоу' + NL + '"' + ' + ' + '"' + NL + '"/vseconds 6 — длительность видео в секундах' + NL + '"'
if s.count(lora_help_ru) == 1:
    s = s.replace(lora_help_ru, lora_help_ru_new, 1)
    print("help ru patched")
lora_help_en = '"/lora — LoRA for both flows: list|name|strength|off' + NL + '"'
lora_help_en_new = '"/lora — LoRA for both flows: list|name|strength|off' + NL + '"' + ' + ' + '"' + NL + '"/tips — prompting tips for the current workflow' + NL + '"' + ' + ' + '"' + NL + '"/vseconds 6 — video duration in seconds' + NL + '"'
if s.count(lora_help_en) == 1:
    s = s.replace(lora_help_en, lora_help_en_new, 1)
    print("help en patched")
open(p2, "w", encoding="utf-8").write(s)
print("strings patched")
