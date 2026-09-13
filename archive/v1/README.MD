## Step 1: Install Dependencies
- Open the command prompt in the ComfyUI portable folder and run:
- python_embeded\python.exe -m pip install websocket-client

## Step 2: Export Workflow
- Open ComfyUI in your browser.

- Click the Gear Icon (Settings) and check Enable Dev mode Options.

- Set up your workflow exactly how you want it.

- Click Save (API Format) and save it as workflow_api.json in the same  folder as the python script.

## Step 3: Initial Run & Config
- Run the script for the first time:
- python_embeded\python.exe telegram_comfy_bot.py

- The script will immediately stop and say it created a bot_config.json file.
- Open bot_config.json in Notepad and fill out:

- telegram_token: The token from @BotFather.

-allowed_users: Your personal Telegram ID (Get it from @userinfobot).

- target_text_node_id: Open workflow_api.json in a text editor, find the "CLIPTextEncode" node that handles your positive prompt, and look at its ID number. (It is usually "6").

## Step 4: Run the Bot
- Run the script again. It will now connect to Telegram and wait for you to send /generate [prompt].