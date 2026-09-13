import json
import urllib.request
import urllib.parse
import websocket
import uuid
import time
import threading
import os
import sys

CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "telegram_token": "YOUR_TELEGRAM_BOT_TOKEN_HERE",
    "allowed_users": [123456789, 987654321],
    "comfyui_server": "127.0.0.1:8188",
    "workflow_file": "workflow_api.json",
    "target_text_node_id": "6"  # Usually 6 for Positive Prompt in default ComfyUI
}

class ConfigManager:
    @staticmethod
    def load_config():
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            print(f"[Setup] Created '{CONFIG_FILE}'. Please fill in your Bot Token and User IDs, then restart.")
            sys.exit(1)
            
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            
        # if config["telegram_token"] == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            # print(f"[Error] Please update the 'telegram_token' inside {CONFIG_FILE}")
            # sys.exit(1)
            
        return config

class ComfyAPI:
    def __init__(self, server_address):
        self.server = server_address

    def queue_prompt(self, workflow):
        p = {"prompt": workflow, "client_id": str(uuid.uuid4())}
        data = json.dumps(p).encode('utf-8')
        req = urllib.request.Request(f"http://{self.server}/prompt", data=data)
        req.add_header("Content-Type", "application/json")
        try:
            response = urllib.request.urlopen(req)
            return json.loads(response.read().decode('utf-8'))
        except urllib.error.URLError:
            print("[Error] Could not connect to ComfyUI. Is it running?")
            return None

    def get_image(self, filename, subfolder, folder_type):
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        try:
            with urllib.request.urlopen(f"http://{self.server}/view?{url_values}") as response:
                return response.read()
        except Exception as e:
            print(f"[Error] Fetching image failed: {e}")
            return None

class TelegramBot:
    def __init__(self, config):
        self.token = config["telegram_token"]
        self.allowed_users = config["allowed_users"]
        self.workflow_file = config["workflow_file"]
        self.target_node_id = config["target_text_node_id"]
        self.comfy = ComfyAPI(config["comfyui_server"])

    def send_message(self, chat_id, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data)
            urllib.request.urlopen(req)
        except Exception as e:
            print(f"[Error] Failed to send Telegram message: {e}")

    def send_photo(self, chat_id, image_bytes, caption=""):
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
        parts = [
            f"--{boundary}",
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}',
            f"--{boundary}",
            f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}',
            f"--{boundary}",
            f'Content-Disposition: form-data; name="photo"; filename="output.png"',
            "Content-Type: image/png\r\n",
            image_bytes,
            f"--{boundary}--\r\n"
        ]
        
        body = b"".join([(p.encode('utf-8') + b'\r\n') if isinstance(p, str) else (p + b'\r\n') for p in parts])
        
        req = urllib.request.Request(url, data=body)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            urllib.request.urlopen(req)
        except Exception as e:
            print(f"[Error] Failed to send photo: {e}")

    def listen_to_comfy_ws(self, prompt_id, chat_id):
        """Connects to ComfyUI WS to track generation progress."""
        try:
            ws = websocket.WebSocket()
            ws.connect(f"ws://{self.comfy.server}/ws")
            
            while True:
                out = ws.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message['type'] == 'executing' and message['data']['node'] is None and message['data']['prompt_id'] == prompt_id:
                        break # Execution complete
                    elif message['type'] == 'executed' and message['data']['prompt_id'] == prompt_id:
                        node_output = message['data']['output']
                        if 'images' in node_output:
                            for img in node_output['images']:
                                img_bytes = self.comfy.get_image(img['filename'], img['subfolder'], img['type'])
                                if img_bytes:
                                    self.send_photo(chat_id, img_bytes, "Generation Complete! ✨")
            ws.close()
        except Exception as e:
            self.send_message(chat_id, "Error tracking image generation.")
            print(f"[WS Error] {e}")

    def handle_generation_request(self, user_prompt, chat_id):
        if not os.path.exists(self.workflow_file):
            self.send_message(chat_id, f"Error: The workflow file '{self.workflow_file}' is missing from the server.")
            return

        with open(self.workflow_file, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # Ensure the targeted node exists and is a text input
        if self.target_node_id not in workflow or "text" not in workflow[self.target_node_id].get("inputs", {}):
            self.send_message(chat_id, f"Configuration Error: Node ID '{self.target_node_id}' does not exist or has no 'text' input.")
            return

        # Inject the new prompt
        workflow[self.target_node_id]["inputs"]["text"] = user_prompt
        self.send_message(chat_id, "Prompt accepted. Firing up the GPU... 🎨")

        prompt_res = self.comfy.queue_prompt(workflow)
        
        if prompt_res and "prompt_id" in prompt_res:
            threading.Thread(target=self.listen_to_comfy_ws, args=(prompt_res["prompt_id"], chat_id), daemon=True).start()
        else:
            self.send_message(chat_id, "Failed to connect to ComfyUI. Check server logs.")

    def start_polling(self):
        print(f"[System] Bot Online. Listening for allowed users: {self.allowed_users}")
        offset = None
        while True:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates?timeout=30"
                if offset:
                    url += f"&offset={offset}"
                    
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req) as response:
                    updates = json.loads(response.read().decode('utf-8'))
                    
                if "result" in updates:
                    for update in updates["result"]:
                        offset = update["update_id"] + 1
                        if "message" in update and "text" in update["message"]:
                            msg = update["message"]
                            chat_id = msg["chat"]["id"]
                            user_id = msg["from"]["id"]
                            text = msg["text"]
                            
                            if user_id not in self.allowed_users:
                                self.send_message(chat_id, f"❌ Access Denied. Your User ID is {user_id}. Add this to bot_config.json to gain access.")
                                continue
                                
                            if text.startswith("/generate "):
                                user_prompt = text.replace("/generate ", "", 1)
                                threading.Thread(target=self.handle_generation_request, args=(user_prompt, chat_id), daemon=True).start()
                            elif text == "/start":
                                self.send_message(chat_id, "Hello! Send `/generate [your idea]` to create an image.")
                                
            except Exception as e:
                print(f"[Warning] Polling error (Network glitch?): {e}")
                time.sleep(5)

if __name__ == "__main__":
    app_config = ConfigManager.load_config()
    bot = TelegramBot(app_config)
    bot.start_polling()