# -*- coding: utf-8 -*-
"""Re-add the /tips per-workflow test (was lost during file cleanup)."""
p = "tests/test_daemon_offline.py"
src = open(p, encoding="utf-8").read()
marker = 'print("OK cnet skipped on video workflow")'
assert src.count(marker) == 1, src.count(marker)
add = marker + '''

# --- prompting tips per workflow ----------------------------------------- #

bot2b.set_chat_workflow(CHAT, "txt2img")
SENT.clear()
bot2b.cmd_tips(CHAT, "")
assert "Z-Image Turbo" in SENT[-1][2], SENT[-1][2]
bot2b.set_chat_workflow(CHAT, "video")
SENT.clear()
bot2b.cmd_tips(CHAT, "")
assert "Wan 2.2 TI2V 5B" in SENT[-1][2] and "ДВИЖЕНИЕ" in SENT[-1][2], SENT[-1][2]
print("OK /tips per workflow")'''
src = src.replace(marker, add, 1)
open(p, "w", encoding="utf-8").write(src)
print("tips test restored")
