import threading
import sys
import os
import traceback

def start_bot_daemon():
    print("\n" + "=" * 50)
    print("[Telegram Bot] Starting background listener...")
    current_dir = os.path.dirname(os.path.realpath(__file__))
    if current_dir not in sys.path:
        sys.path.append(current_dir)

    try:
        from .telegram_daemon import start_bot_daemon as run_daemon
        run_daemon()
    except Exception:
        print("[Telegram Bot] FAILED to start daemon:")
        traceback.print_exc()
    print("=" * 50 + "\n")

start_bot_daemon()

# Expose the manual node to the ComfyUI UI (Deliberately avoiding try/except to expose import errors)
from .save_to_phone import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
