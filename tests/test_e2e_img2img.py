# -*- coding: utf-8 -*-
"""E2E test for img2img: fake only the Telegram file download, everything else is real."""
import copy
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import telegram_daemon as td

td.setup_logging()

config = td.load_config()
assert config, "no valid config"
bot = td.ControlBot(config)
CHAT = (config.get("allowed_users") or [0])[0]

# a real 512x768 gradient test image (PIL is available in the venv)
from PIL import Image
img = Image.new("RGB", (512, 768))
for y in range(768):
    for step in range(0, 512, 64):
        for x in range(step, min(step + 64, 512)):
            img.putpixel((x, y), (step * 255 // 512, y * 255 // 768, 128))
buf = io.BytesIO()
img.save(buf, format="PNG")
fake_blob = buf.getvalue()

# only the Telegram download is stubbed; upload/queue/generation/delivery are real
bot.api.download_file = lambda file_id: fake_blob

# switch this chat to img2img, run the full command path
bot.set_chat_workflow(CHAT, "img2img")
bot.cmd_generate(CHAT, "тест img2img: зебра в скафандре 🦓", {"file_id": "e2e", "ext": "png"})
print("E2E IMG2IMG DONE")
