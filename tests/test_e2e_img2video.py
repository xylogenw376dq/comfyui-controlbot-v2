# -*- coding: utf-8 -*-
"""E2E: img2video — photo + prompt -> mp4, delivered to the owner chat."""
import io
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
PLUGIN_DIR = r"C:\Users\xlgn\AppData\Local\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\comfyui-controlbot"
sys.path.insert(0, PLUGIN_DIR)

import telegram_daemon as td
from PIL import Image

td.setup_logging()

config = td.load_config()
bot = td.ControlBot(config)
CHAT = (config.get("allowed_users") or [0])[0]

# first frame: a simple landscape (real PNG, 1024x576 ~ video aspect)
img = Image.new("RGB", (1024, 576), (90, 130, 180))
d = ImageDraw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(img)
d.rectangle([0, 380, 1024, 576], fill=(60, 90, 50))          # ground
d.rectangle([420, 200, 620, 380], fill=(150, 80, 60))        # cabin body
d.polygon([(380, 200), (520, 120), (660, 200)], fill=(90, 60, 40))  # roof
buf = io.BytesIO()
img.save(buf, format="PNG")

bot.api.download_file = lambda file_id: (buf.getvalue(), None)  # stub Telegram download only

bot.set_chat_workflow(CHAT, "video")
bot.cmd_generate(CHAT, "a cozy cabin in the mountains, clouds drifting, cinematic")

# keep the process alive while the tracker delivers (video gen is slow)
print("img2video queued — waiting for delivery...", flush=True)
deadline = time.time() + 35 * 60
delivered = False
while time.time() < deadline and not delivered:
    time.sleep(5)
    last = (bot.state.load().get("last")) or {}
    if last.get("prompt_id") and last.get("images"):
        delivered = True
print("E2E IMG2VIDEO DONE, delivered:", delivered)
