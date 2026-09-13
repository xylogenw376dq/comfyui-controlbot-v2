# Архитектура

## Запуск и живучесть

```
ComfyUI импортирует custom_node
  └─ __init__.py → start_bot_daemon()
       ├─ поток supervisor: конфиг → ControlBot → setMyCommands → run_polling()
       │    └─ падение → перезапуск с задержкой 5с…2мин
       └─ поток watchdog (раз в минуту):
            - supervisor умер → перезапустить
            - heartbeat полинга устарел (>10 мин) → тревога в лог
```

Бот — daemon-поток внутри процесса ComfyUI: стартует и умирает вместе с ним.
Состояние (аптайм, перезапуски, апдейты) видно в `/status`.

## Опрос и обновления

`getUpdates` long-poll (30с) с heartbeat'ом; принимаются `message` и `callback_query`.
Каждое сообщение обрабатывается в отдельном потоке. Конфиг перечитывается при изменении
mtime `config.json` (без перезапуска подхватываются пользователи, админы, язык).

## Обработка генерации

```
/generate
  → load_workflow (активный workflow чата)
  → apply_overrides (overrides.json, sentinel "random" → случайный seed)
  → inject_lora (LoraLoader: base model → LoRA, model + CLIP)
  → inject_controlnet (ModelPatchLoader → ZImageFunControlnet: base → LoRA → ControlNet)
  → POST /prompt
  → track_and_deliver (поток):
       - websocket ComfyUI: прогресс семплера → ETA в статусном сообщении (правки каждые 5с)
       - /history: все output-ноды, дедупликация
       - 1 картинка → sendPhoto, 2-10 → альбом, >10 → пачками
       - задача исчезла из очереди → сообщение (отмена/рестарт), не ждём таймаут
```

## ControlNet-маска

```
фото с подписью /cnet
  → download (Telegram) → upload (ComfyUI /upload/image)
  → временный workflow: LoadImage → AIO_Preprocessor → SaveImage
  → превью маски в чат + inline-кнопки ✅/✖️ (callback_query)
  → approve: маска загружается в input как отдельный файл и сохраняется в chat_settings
  → используется во всех генерациях до /cnet clear
```

Инъекция ControlNet валидирует, что маска есть в актуальном списке LoadImage
(`/object_info` запрашивается без кэша — список input-папки меняется).

## Переопределения и хранилища

Все хранилища — атомарные JSON через `JsonStore` (tmp + os.replace, блокировки).

- `overrides.json` — `/set`: `{nodes: {id: {param: value}}, prompt}`; sentinel `random`
  для seed-параметров превращается в случайное число при постановке в очередь
- `chat_settings.json` — per-chat: язык, workflow, LoRA, ControlNet-маска
- `state.json` — последняя генерация для `/last` и `/regen`

Валидация значений — по схеме `/object_info`: INT/FLOAT с диапазоном, combo с
частичным совпадением, STRING-приведение; список файлов всегда запрашивается свежим.

## Локализация

`bot_strings.py`: `STRINGS[lang][key]`, русский — fallback. Меню команд регистрируется
глобально в языке по умолчанию и per-chat (scope `chat`) для чатов с нестандартным языком.
Персональное меню создаётся только если язык чата отличается от дефолтного.
Тест `i18n coverage` сканирует исходники и требует наличия всех использованных ключей
в обоих языках.
