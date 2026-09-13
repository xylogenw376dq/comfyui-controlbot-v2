import threading
import json
import os
import time
import urllib.request
import urllib.parse
import uuid
import requests 

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WORKFLOW_PATH = os.path.join(BASE_DIR, "workflow_api.json")

def load_or_create_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w') as f:
            json.dump({
                "telegram_token": "YOUR_BOT_TOKEN_HERE",
                "allowed_users": [123456789],
                "comfy_host": "127.0.0.1:8188"
            }, f, indent=4)
        print("\n[Telegram Bot] ⚠️ Created config.json. Please add your token and restart.\n")
        return None
        
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
        if config.get("telegram_token") == "YOUR_BOT_TOKEN_HERE":
            return None
        return config

def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception:
        pass

def send_photo_reliable(token, chat_id, image_bytes, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {'photo': ('output.png', image_bytes, 'image/png')}
    data = {'chat_id': chat_id, 'caption': caption}
    try:
        requests.post(url, data=data, files=files, timeout=30)
    except Exception:
        pass

def fetch_image(host, filename, subfolder, folder_type):
    data = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
    try:
        with urllib.request.urlopen(f"http://{host}/view?{data}") as response:
            return response.read()
    except Exception:
        return None

def track_and_deliver(prompt_id, chat_id, config, user_prompt):
    history_url = f"http://{config['comfy_host']}/history/{prompt_id}"
    attempts = 0
    
    while attempts < 120: 
        try:
            with urllib.request.urlopen(urllib.request.Request(history_url)) as response:
                history_data = json.loads(response.read().decode('utf-8'))
                
            if prompt_id in history_data:
                outputs = history_data[prompt_id].get("outputs", {})
                
                for node_id, node_output in outputs.items():
                    if 'images' in node_output:
                        for img in node_output['images']:
                            img_data = fetch_image(config['comfy_host'], img['filename'], img['subfolder'], img['type'])
                            if img_data:
                                send_photo_reliable(config['telegram_token'], chat_id, img_data, f"🎨 {user_prompt}")
                                return
                
                send_message(config['telegram_token'], chat_id, "Generation finished, but no image was saved by the workflow.")
                return
        except Exception:
            pass 
            
        time.sleep(2)
        attempts += 1

def find_positive_prompt_node(workflow):
    # Strategy 1: Find the KSampler and trace its positive wire backward
    for node_id, node in workflow.items():
        if node.get("class_type") in ["KSampler", "KSamplerAdvanced"]:
            positive_wire = node.get("inputs", {}).get("positive")
            if positive_wire and isinstance(positive_wire, list):
                return str(positive_wire[0])
                
    # Strategy 2: Fallback to the first text box found
    for node_id, node in workflow.items():
        if node.get("class_type") == "CLIPTextEncode" and "text" in node.get("inputs", {}):
            return str(node_id)
            
    return None

def process_prompt(user_prompt, chat_id, config):
    if not os.path.exists(WORKFLOW_PATH):
        send_message(config['telegram_token'], chat_id, "Error: workflow_api.json missing from the server.")
        return

    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    node_id = find_positive_prompt_node(workflow)
    
    if not node_id or "text" not in workflow[node_id].get("inputs", {}):
        send_message(config['telegram_token'], chat_id, "Error: Could not automatically locate the text box in the workflow.")
        return

    workflow[node_id]["inputs"]["text"] = user_prompt
    
    try:
        data = json.dumps({"prompt": workflow, "client_id": str(uuid.uuid4())}).encode('utf-8')
        req = urllib.request.Request(f"http://{config['comfy_host']}/prompt", data=data, headers={"Content-Type": "application/json"})
        response = urllib.request.urlopen(req)
        prompt_res = json.loads(response.read().decode('utf-8'))
        
        send_message(config['telegram_token'], chat_id, "Prompt queued. Firing up the GPU...")
        threading.Thread(target=track_and_deliver, args=(prompt_res["prompt_id"], chat_id, config, user_prompt), daemon=True).start()
    except Exception:
        send_message(config['telegram_token'], chat_id, "Error: Failed to connect to the ComfyUI queue.")

def polling_loop():
    config = load_or_create_config()
    if not config: return
    
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{config['telegram_token']}/getUpdates?timeout=30"
            if offset: url += f"&offset={offset}"
            
            with urllib.request.urlopen(urllib.request.Request(url)) as response:
                updates = json.loads(response.read().decode('utf-8'))
                
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update and "text" in update["message"]:
                    msg = update["message"]
                    chat_id, user_id, text = msg["chat"]["id"], msg["from"]["id"], msg["text"]
                    
                    if user_id not in config["allowed_users"]:
                        continue
                        
                    if text.startswith("/generate "):
                        prompt = text.replace("/generate ", "", 1)
                        threading.Thread(target=process_prompt, args=(prompt, chat_id, config), daemon=True).start()
        except Exception:
            time.sleep(5)

def start_bot_daemon():
    threading.Thread(target=polling_loop, daemon=True).start()