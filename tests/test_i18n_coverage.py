# -*- coding: utf-8 -*-
"""i18n coverage: every key used in telegram_daemon.py must exist in every language."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "telegram_daemon.py"), encoding="utf-8").read()
sys_mod = open(os.path.join(HERE, "..", "bot_strings.py"), encoding="utf-8").read()

used = set(re.findall(r"\.t\(\s*chat_id,\s*[\"']([a-z_]+)[\"']", src, re.S))
used |= set(re.findall(r"MsgError\(\s*[\"']([a-z_]+)[\"']", src))
used |= {"seed_random", "seed_increment", "seed_decrement"}  # f"seed_{mode}" is dynamic

# ключи должны быть в STRINGS обоих языков
ns = {}
exec(compile(open(os.path.join(HERE, "..", "bot_strings.py"), encoding="utf-8").read(), "bot_strings.py", "exec"), ns)
strings = ns["STRINGS"]

for lang in ("ru", "en"):
    missing = used - set(strings[lang])
    assert not missing, f"missing keys in {lang}: {missing}"
print(f"OK i18n coverage: {len(used)} keys present in ru+en")
