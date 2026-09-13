# <img src="docs/img/icon.png" width="36" align="top" alt=""> comfyui-controlbot v2

A Telegram bot that drives ComfyUI from your phone: image generation, workflow parameter
tuning, LoRA, ControlNet — without opening the UI.

Languages: [Русский](README.md) · **English** · [中文](README.zh-CN.md)

This is a ground-up **second version** of
[AbhishekJha3511/comfyui-controlbot](https://github.com/AbhishekJha3511/comfyui-controlbot):
only the idea ("a bot that sends you pictures") survived from v1, the code is a full rewrite.
See [docs/changelog.md](docs/changelog.md) for details.

## Features

- `/generate` — txt2img and img2img (photo + caption or reply), progress with ETA every 5 seconds
- `/workflow video` — img2video (Wan 2.2 TI2V 5B): photo → mp4 clip
- `/workflow` — multiple API workflows, switched per chat
- `/cnet` — ControlNet (Z-Image Fun Union) with mask approval via inline buttons
- `/lora` — single active LoRA, picked from a list, persisted until reset
- `/set`, `/params` and shortcuts — tune any workflow parameter from chat
- `/status`, `/queue`, `/stop`, `/last`, `/regen` — generation control
- `/adduser`, `/deluser` — access management (admins are set in config)
- `/lang` — ru/en localization per chat
- Command menu, albums for multi-image runs, self-healing supervisor + watchdog

## Standard models

The bundled workflows target **Z-Image Turbo** and work out of the box with the following
models (folders are inside `ComfyUI/models/`; on ComfyUI Desktop it's `ComfyUI-Shared/models/`):

| Component | File | Put it in | Source |
|---|---|---|---|
| Diffusion model | `z_image_turbo_bf16.safetensors` (12.3 GB) | `diffusion_models/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors) |
| Text encoder | `qwen_3_4b.safetensors` (8 GB) | `text_encoders/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors) |
| VAE | `ae.safetensors` (0.34 GB) | `vae/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors) |
| Seed node (custom node) | ComfyUI-RandomSeedGenerator | `custom_nodes/` | [GitHub](https://github.com/Limbicnation/ComfyUI-RandomSeedGenerator) |
| ControlNet *(optional)* | `Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors` (~6.7 GB) | `model_patches/` | [HuggingFace](https://huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1/resolve/main/Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors) + the [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) pack for modes |
| Example LoRA *(optional)* | `aesthetic_exp1.safetensors` | `loras/` | [Civitai](https://civitai.com/models/689192/aesthetic-amateur-photo?modelVersionId=2558476) |

ControlNet and the LoRA are optional extensions; everything else is required by the bundled workflows.

## Install

1. Copy the folder into `ComfyUI/custom_nodes/`.
2. Copy `config.example.json` → `config.json`, fill in the @BotFather token and your Telegram ID.
3. Export your workflow from ComfyUI ("Export (API)") as `workflow_api.json`,
   or use the bundled `workflow_api.json` / `workflow_img2img_api.json` with the models above.
4. For ControlNet put the model into `models/model_patches/` (see [docs/configuration.md](docs/configuration.md)).

One dependency — `requests` (already present in the ComfyUI environment).

## Run

Restart ComfyUI — the bot starts automatically with it (a background thread;
a supervisor + watchdog restart it on crashes). Logs: `bot.log` in the plugin folder.

## Verify

1. In the bot chat: `/help` — you should get the command reference; typing "/" shows the menu.
2. `/status` — a reply with the ComfyUI version, VRAM and the bot health line.
3. `/generate an astronaut cat` — an image arrives in ~15 seconds.

## Commands

Full reference with examples — [docs/commands.md](docs/commands.md). Key ones:
`/generate`, `/workflow`, `/cnet`, `/lora`, `/set`, `/status`, `/lang`, `/help`.

## Documentation

The docs are in Russian: [commands](docs/commands.md), [configuration](docs/configuration.md),
[architecture](docs/architecture.md), [changelog](docs/changelog.md), [testing](docs/testing.md).

## Credits

Original idea and v1 — [AbhishekJha3511](https://github.com/AbhishekJha3511/comfyui-controlbot).
