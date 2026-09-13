# comfyui-controlbot v2

Телеграм-бот, который управляет ComfyUI с телефона: генерация картинок, настройка параметров
workflow, LoRA, ControlNet — без открытия интерфейса.

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
