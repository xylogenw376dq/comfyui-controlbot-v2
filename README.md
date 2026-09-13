# comfyui-controlbot v2

Телеграм-бот, который управляет ComfyUI с телефона: генерация картинок, настройка параметров
workflow, LoRA, ControlNet — без открытия интерфейса.

Другие языки: [English](README.en.md) · [中文](README.zh-CN.md)

Это переработанная **вторая версия** плагина
[AbhishekJha3511/comfyui-controlbot](https://github.com/AbhishekJha3511/comfyui-controlbot):
от v1 здесь осталась только идея «бот присылает картинку», код переписан полностью.
Что именно изменилось — в [docs/changelog.md](docs/changelog.md).

## Возможности

- `/generate` — txt2img и img2img (фото + подпись или reply), прогресс с ETA каждые 5 секунд
- `/workflow` — несколько API-workflow с переключением per-chat
- `/cnet` — ControlNet (Z-Image Fun Union) с одобрением маски через inline-кнопки
- `/lora` — одна активная LoRA, выбор из списка, сохраняется до сброса
- `/set`, `/params` и шорткаты — настройка любого параметра workflow из чата
- `/status`, `/queue`, `/stop`, `/last`, `/regen` — управление генерацией
- `/adduser`, `/deluser` — управление доступом (админы задаются в конфиге)
- `/lang` — локализация ru/en per-chat
- Меню команд, альбомы при мульти-генерации, автоперезапуск с watchdog'ем

## Стандартные модели

Приложенные workflows рассчитаны на **Z-Image Turbo** и работают из коробки со следующими моделями
(папки — внутри `ComfyUI/models/`, в ComfyUI Desktop это `ComfyUI-Shared/models/`):

| Компонент | Файл | Куда положить | Откуда |
|---|---|---|---|
| Диффузионная модель | `z_image_turbo_bf16.safetensors` (12.3 ГБ) | `diffusion_models/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors) |
| Текстовый энкодер | `qwen_3_4b.safetensors` (8 ГБ) | `text_encoders/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors) |
| VAE | `ae.safetensors` (0.34 ГБ) | `vae/` | [HuggingFace](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors) |
| Seed-нода (custom node) | ComfyUI-RandomSeedGenerator | `custom_nodes/` | [GitHub](https://github.com/Limbicnation/ComfyUI-RandomSeedGenerator) |
| ControlNet *(опционально)* | `Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors` (~6.7 ГБ) | `model_patches/` | [HuggingFace](https://huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1/resolve/main/Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors) + пак [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) для режимов |
| LoRA-пример *(опционально)* | `aesthetic_exp1.safetensors` | `loras/` | [Civitai](https://civitai.com/models/689192/aesthetic-amateur-photo?modelVersionId=2558476) |

ControlNet и LoRA — необязательные расширения, остальное нужно для работы приложенных workflows.

## Установка

1. Скопируйте папку в `ComfyUI/custom_nodes/` (ComfyUI Desktop: `ComfyUI-Installs\...\custom_nodes`).
2. Скопируйте `config.example.json` → `config.json` и впишите токен от @BotFather и свой Telegram ID.
3. Экспортируйте свой workflow в ComfyUI («Export (API)») как `workflow_api.json`
   или используйте приложенные `workflow_api.json` / `workflow_img2img_api.json`.
4. Для ControlNet положите модель в `models/model_patches/` (см. [docs/configuration.md](docs/configuration.md)).

Зависимость одна — `requests` (уже есть в окружении ComfyUI).

## Запуск

Перезапустите ComfyUI — бот стартует автоматически вместе с ним (фоновый поток,
supervisor + watchdog перезапускают его при сбоях). Лог: `bot.log` в папке плагина.

## Проверка

1. В чате с ботом: `/help` — должно прийти описание команд, при вводе «/» видно меню.
2. `/status` — ответ с версией ComfyUI, VRAM и строкой здоровья бота.
3. `/generate кот-космонавт` — через ~15 секунд приходит картинка.

## Команды

Полный список с примерами — [docs/commands.md](docs/commands.md). Ключевые:
`/generate`, `/workflow`, `/cnet`, `/lora`, `/set`, `/status`, `/lang`, `/help`.

## Документация

- [docs/commands.md](docs/commands.md) — справочник команд
- [docs/configuration.md](docs/configuration.md) — config.json, хранилища, модели, LoRA
- [docs/architecture.md](docs/architecture.md) — как всё устроено внутри
- [docs/changelog.md](docs/changelog.md) — изменения относительно v1
- [docs/testing.md](docs/testing.md) — офлайн-тесты и e2e-скрипты

## Credits

Идея и первая версия — [AbhishekJha3511](https://github.com/AbhishekJha3511/comfyui-controlbot).
