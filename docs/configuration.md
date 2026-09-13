# Конфигурация

## config.json

Создаётся из `config.example.json`. Плагин читает его при старте и **следит за изменениями**:
`allowed_users`, `admins`, `lora_aliases` подхватываются на лету, смена токена перезапускает бота.

| Поле | Описание |
|---|---|
| `telegram_token` | Токен бота от @BotFather |
| `allowed_users` | Telegram ID, которым разрешено писать боту. Пополняется командой `/adduser` |
| `admins` | Админы (управление пользователями, ControlNet/LoRA/язык в группах). Только вручную, нужен перезапуск |
| `comfy_host` | Адрес API ComfyUI |
| `workflows` | Карта «имя → файл API-workflow». Имена из этой карты — аргументы `/workflow` |
| `default_workflow` | Активный workflow для новых чатов |
| `default_language` | Язык по умолчанию (`ru` / `en`) |
| `lora_aliases` | Карта «короткое имя → файл в models/loras/» для `/lora` |
| `generation_timeout` | Сколько секунд ждать результат (по умолчанию 1800) |
| `progress_edit_interval` | Период обновления статуса генерации (минимум 3с, по умолчанию 5) |

## Файлы плагина

| Файл | Что это | В git |
|---|---|---|
| `config.json` | Рабочий конфиг с токеном | ❌ (.gitignore) |
| `overrides.json` | Переопределения параметров из `/set` | ❌ |
| `chat_settings.json` | Язык, workflow, LoRA, маска ControlNet для каждого чата | ❌ |
| `state.json` | Данные последней генерации (`/last`, `/regen`) | ❌ |
| `bot.log*` | Лог (ротация 1 МБ × 3) | ❌ |
| `workflow_api.json`, `workflow_img2img_api.json` | Базовые API-workflow | ✅ |

## Модели

**ControlNet** — модель `Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors` (~6.7 ГБ,
[alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1](https://huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1))
кладётся в `ComfyUI/models/model_patches/`. Режимы (bones/depth/canny/…) даёт пак
[comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) — он нужен только для них,
сам ControlNet работает на нодах ядра (`ModelPatchLoader` + `Apply Z-Image Fun ControlNet`).

**LoRA** — файлы в `ComfyUI/models/loras/`, только под архитектуру Z-Image.

**img2video** (`/workflow video`) — модель `wan2.2_ti2v_5B_fp16.safetensors` (10 ГБ) в
`diffusion_models/`, энкодер `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6.7 ГБ) в
`text_encoders/`, VAE `wan_2.1_vae.safetensors` в `vae/` — всё из
[Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged).
На карте с 8 ГБ VRAM клип 1280×704×49 кадров генерируется ~10–20 минут со стримингом весов.
Имена в боте задаются через `lora_aliases` в config.json.

## Требования к workflow

- Формат API («Export (API)» в редакторе ComfyUI)
- Для генерации по промпту — нода с текстом, достижимая от `positive` входа сэмплера
  (обход графа от KSampler/SamplerCustom… до первой ноды с текстом)
- Для img2img — нода `LoadImage` (бот подменяет в ней файл)
- Для ControlNet — `ModelPatchLoader` + `ZImageFunControlnet` встраиваются ботом автоматически
