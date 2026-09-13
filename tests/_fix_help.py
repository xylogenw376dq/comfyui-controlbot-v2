# -*- coding: utf-8 -*-
"""Final: remove DBG prints, make vseconds test hermetic, pin workflows in tests."""
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- 1) telegram_daemon.py: remove temporary DBG prints ---
p = "telegram_daemon.py"
src = open(p, encoding="utf-8").read()
dbg1 = '        print("DBG1 lora alias:", self.get_lora_settings(chat_id).get("alias"))\n'
dbg4 = '        print("DBG4 reached cnet block")\n'
n1, n4 = src.count(dbg1), src.count(dbg4)
src = src.replace(dbg1, "").replace(dbg4, "")
open(p, "w", encoding="utf-8").write(src)
print(f"DBG removed: {n1}, {n4}")

# --- 2) tests: hermetic vseconds test ---
p = "tests/test_daemon_offline.py"
src = open(p, encoding="utf-8").read()
old = '''wf_v = bot2b.load_active_workflow(CHAT)
wf_v["90"]["inputs"]["fps"] = 30
bot2b.load_active_workflow = lambda cid: wf_v
bot2b.cmd_vseconds(CHAT, "6")
assert "30 fps" in SENT[-1][2] and "180 кадров" in SENT[-1][2], SENT[-1][2]
assert td.plan_video_segments(180) == [81, 81, 17], td.plan_video_segments(180)  # 17 = nearest 4n+1 to 18
print("OK /vseconds fps-aware")'''
new = '''import copy as _copy
orig_law = bot2b.load_active_workflow
wf_v = _copy.deepcopy(bot2b.load_active_workflow(CHAT))
wf_v["90"]["inputs"]["fps"] = 30
bot2b.load_active_workflow = lambda cid: _copy.deepcopy(wf_v)
bot2b.cmd_vseconds(CHAT, "6")
assert "30 fps" in SENT[-1][2] and "180 кадров" in SENT[-1][2], SENT[-1][2]
assert td.plan_video_segments(180) == [81, 81, 17], td.plan_video_segments(180)  # 17 = nearest 4n+1 to 18
bot2b.load_active_workflow = orig_law
bot2b.set_video_settings(CHAT, seconds=2)
print("OK /vseconds fps-aware")'''
assert src.count(old) == 1, ("vsec", src.count(old))
src = src.replace(old, new, 1)

old2 = '''# with a photo -> I2V mode keeps start_image wired
POSTED.clear()
bot2b.cmd_generate(CHAT, "clouds drifting", {"file_id": "good", "ext": "jpg"})'''
new2 = '''# with a photo -> I2V mode keeps start_image wired
bot2b.set_chat_workflow(CHAT, "video")
POSTED.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "clouds drifting", {"file_id": "good", "ext": "jpg"})'''
assert src.count(old2) == 1, ("i2v", src.count(old2))
src = src.replace(old2, new2, 1)

old3 = '''bot2b.set_cnet_settings(CHAT, enabled=True, mask_name="mask.png", prep="", seconds=2)
POSTED.clear()
SENT.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "clouds drifting")'''
new3 = '''bot2b.set_video_settings(CHAT, seconds=2)
bot2b.set_chat_workflow(CHAT, "video")
POSTED.clear()
SENT.clear()
bot2b.comfy = PostingComfy()
bot2b.cmd_generate(CHAT, "clouds drifting")'''
assert src.count(old3) == 1, ("cnet", src.count(old3))
src = src.replace(old3, new3, 1)
open(p, "w", encoding="utf-8").write(src)
print("tests made hermetic")
