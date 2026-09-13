# -*- coding: utf-8 -*-
"""E2E: controlnet mask pipeline + generation with the approved mask (txt2img)."""
import sys

sys.stdout.reconfigure(encoding="utf-8")
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import telegram_daemon as td

td.setup_logging()

config = td.load_config()
bot = td.ControlBot(config)
CHAT = (config.get("allowed_users") or [0])[0]

# --- a stick figure: "определённая поза" ---
from PIL import Image, ImageDraw
img = Image.new("RGB", (512, 768), "white")
d = ImageDraw.Draw(img)
BLACK = (10, 10, 10)
d.ellipse([216, 60, 296, 140], outline=BLACK, width=10)          # head
d.line([256, 140, 256, 400], fill=BLACK, width=12)               # spine
d.line([256, 220, 150, 320], fill=BLACK, width=12)               # left arm
d.line([256, 220, 362, 320], fill=BLACK, width=12)               # right arm
d.line([256, 400, 170, 580], fill=BLACK, width=12)               # left leg
d.line([256, 400, 342, 580], fill=BLACK, width=12)               # right leg
import io
buf = io.BytesIO()
img.save(buf, format="PNG")
ref_blob = buf.getvalue()

# only the Telegram download is stubbed; everything else is real
bot.api.download_file = lambda file_id: (ref_blob, None)

# 1) reference -> mask preview (raw, no preprocessor) -> pending
bot.set_chat_workflow(CHAT, "txt2img")
bot.cmd_cnet(CHAT, "", "private", 1, {"file_id": "e2e", "ext": "png"})
assert str(CHAT) in bot._pending_masks, "no pending mask"
print("1. mask preview sent, pending approval")

# 2) approve -> mask stored in ComfyUI input
assert bot._approve_mask(CHAT) is None
mask_name = bot.get_cnet_settings(CHAT)["mask_name"]
assert mask_name, "mask not stored"
print("2. mask approved:", mask_name)

# 3) enable controlnet and generate with the mask (txt2img)
bot.set_cnet_settings(CHAT, enabled=True, strength=0.8)
bot.cmd_generate(CHAT, "professional full body photo of a person standing with arms out, studio light")
print("3. generation with controlnet queued and delivered")
print("E2E CONTROLNET DONE")
