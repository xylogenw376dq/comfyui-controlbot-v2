# -*- coding: utf-8 -*-
"""E2E test: queue a batch-2 generation and deliver the album to the real chat."""
import copy
import sys

sys.stdout.reconfigure(encoding="utf-8")
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

import telegram_daemon as td

td.setup_logging()  # the e2e log goes to bot.log too, so ws progress is verifiable

config = td.load_config()
assert config, "no valid config"
bot = td.ControlBot(config)
CHAT = (config.get("allowed_users") or [0])[0]

# Simulate /set batch 2
overrides = {"prompt": None, "nodes": {"57:13": {"batch_size": 2}}}
bot.overrides.save(overrides)

workflow = bot.load_workflow()
prompt_text = "Тест мульти-доставки: две картинки 🧪"
bot.apply_overrides(workflow, overrides)
nid = td.find_positive_prompt_node(workflow)
workflow[nid]["inputs"]["text"] = prompt_text

prompt_id, client_id, err = bot.queue_workflow(chat_id=CHAT, workflow=workflow)
assert prompt_id, f"queue failed: {err}"
print("queued:", prompt_id, flush=True)

# synchronous delivery (same code path the tracker thread runs); client_id enables ws progress
bot.track_and_deliver(CHAT, prompt_id, prompt_text, copy.deepcopy(workflow), client_id)

# leave overrides clean for the user
bot.overrides.save({"prompt": None, "nodes": {}})
print("E2E DONE")
