# -*- coding: utf-8 -*-
"""Temporary trace patch to find the silent-return path in cmd_generate."""
p = "telegram_daemon.py"
src = open(p, encoding="utf-8").read()

old = """        # LoRA patch (both flows) — wired before ControlNet so the chain is
        # base model → LoRA → ControlNet → sampler
        if self.get_lora_settings(chat_id).get("alias"):"""
new = """        # LoRA patch (both flows) — wired before ControlNet so the chain is
        # base model → LoRA → ControlNet → sampler
        print("DBG1 lora alias:", self.get_lora_settings(chat_id).get("alias"))
        if self.get_lora_settings(chat_id).get("alias"):"""
assert src.count(old) == 1
src = src.replace(old, new, 1)

old2 = """        if not alias:
            return workflow, None
        lora_file = self.lora_aliases().get(alias)"""
new2 = """        if not alias:
            print("DBG2 inject_lora: no alias")
            return workflow, None
        lora_file = self.lora_aliases().get(alias)"""
assert src.count(old2) == 1
src = src.replace(old2, new2, 1)

old3 = """        if not is_wire(old_model) or not is_wire(old_clip):
            return workflow, MsgError("lora_need_sampler")"""
new3 = """        if not is_wire(old_model) or not is_wire(old_clip):
            print("DBG3 inject_lora: wires fail", old_model, old_clip)
            return workflow, MsgError("lora_need_sampler")"""
assert src.count(old3) == 1
src = src.replace(old3, new3, 1)

old4 = """        if self.get_cnet_settings(chat_id).get("enabled"):
            if self.is_video_workflow(workflow):"""
new4 = """        print("DBG4 reached cnet block")
        if self.get_cnet_settings(chat_id).get("enabled"):
            if self.is_video_workflow(workflow):"""
assert src.count(old4) == 1
src = src.replace(old4, new4, 1)
open(p, "w", encoding="utf-8").write(src)
print("trace added")
