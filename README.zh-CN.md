# <img src="docs/img/icon.png" width="36" align="top" alt=""> comfyui-controlbot v2

一个通过 Telegram 控制 ComfyUI 的机器人：在手机上完成图像生成、工作流参数调节、
LoRA 和 ControlNet，无需打开界面。

语言：[Русский](README.md) · [English](README.en.md) · **中文**

这是 [AbhishekJha3511/comfyui-controlbot](https://github.com/AbhishekJha3511/comfyui-controlbot)
的**第二个重写版本**：v1 只保留了"机器人发图"这个想法，代码完全重写。
具体变更见 [docs/changelog.md](docs/changelog.md)。

## 功能

- `/generate` — txt2img 与 img2img（图片加说明文字或回复图片），每 5 秒更新带 ETA 的进度
- `/workflow` — 多套 API 工作流，按聊天独立切换
- `/cnet` — ControlNet（Z-Image Fun Union），通过内联按钮确认遮罩
- `/lora` — 单个激活的 LoRA，从列表选择，保存到重置为止
- `/set`、`/params` 及快捷命令 — 在聊天中调节工作流的任意参数
- `/status`、`/queue`、`/stop`、`/last`、`/regen` — 生成控制
- `/adduser`、`/deluser` — 用户管理（管理员在配置文件中设置）
- `/lang` — 按聊天独立的俄/英本地化
- 命令菜单、多图相册发送、带 watchdog 的自动重启

## 标准模型

自带的 workflow 基于 **Z-Image Turbo**，配合以下模型即可开箱即用
（文件夹位于 `ComfyUI/models/` 内；ComfyUI Desktop 则是 `ComfyUI-Shared/models/`）：

| 组件 | 文件 | 放置目录 | 来源 |
|---|---|---|---|
| 扩散模型 | `z_image_turbo_bf16.safetensors` (12.3 GB) | `diffusion_models/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors) |
| 文本编码器 | `qwen_3_4b.safetensors` (8 GB) | `text_encoders/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors) |
| VAE | `ae.safetensors` (0.34 GB) | `vae/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors) |
| Seed 节点（自定义节点） | ComfyUI-RandomSeedGenerator | `custom_nodes/` | [GitHub](https://github.com/Limbicnation/ComfyUI-RandomSeedGenerator) |
| ControlNet（可选） | `Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors` (~6.7 GB) | `model_patches/` | [HuggingFace](https://huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1/resolve/main/Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors)，模式需要 [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) 插件 |
| LoRA 示例（可选） | `aesthetic_exp1.safetensors` | `loras/` | [Civitai](https://civitai.com/models/689192/aesthetic-amateur-photo?modelVersionId=2558476) |

ControlNet 和 LoRA 是可选扩展；其余为自带 workflow 所必需。

## 安装

1. 将本文件夹复制到 `ComfyUI/custom_nodes/`。
2. 将 `config.example.json` 复制为 `config.json`，填入 @BotFather 的机器人令牌和你的 Telegram ID。
3. 在 ComfyUI 中把你的工作流以「Export (API)」导出为 `workflow_api.json`，
   或直接使用自带的 `workflow_api.json` / `workflow_img2img_api.json` 及上述模型。
4. 如需 ControlNet，将模型放入 `models/model_patches/`（详见 [docs/configuration.md](docs/configuration.md)）。

唯一依赖是 `requests`（ComfyUI 环境中已存在）。

## 运行

重启 ComfyUI — 机器人随其自动启动（后台线程；supervisor + watchdog 在崩溃时自动重启）。
日志在插件目录的 `bot.log`。

## 验证

1. 在与机器人的对话中发送 `/help` — 应返回命令说明；输入「/」会显示菜单。
2. `/status` — 返回 ComfyUI 版本、显存及机器人健康状态。
3. `/generate 一只宇航员猫` — 约 15 秒后收到图片。

## 命令

完整参考见 [docs/commands.md](docs/commands.md)。主要命令：
`/generate`、`/workflow`、`/cnet`、`/lora`、`/set`、`/status`、`/lang`、`/help`。

## 文档

文档为俄语：[commands](docs/commands.md)、[configuration](docs/configuration.md)、
[architecture](docs/architecture.md)、[changelog](docs/changelog.md)、[testing](docs/testing.md)。

## Credits

创意与第一版 — [AbhishekJha3511](https://github.com/AbhishekJha3511/comfyui-controlbot)。
