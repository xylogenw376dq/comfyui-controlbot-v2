"""User-facing strings for the ComfyUI Telegram bot, per-chat localization.

Russian is the default/fallback language. Templates use str.format()
placeholders; literal braces must be avoided (or doubled).
"""

DEFAULT_LANGUAGE = "ru"

LANGUAGES = {
    "ru": "Русский 🇷🇺",
    "en": "English 🇬🇧",
}

# Telegram command menu: (command, {lang: description})
MENU = [
    ("generate", {"ru": "🎨 Сгенерировать: /generate описание",
                  "en": "🎨 Generate: /generate description"}),
    ("prompt", {"ru": "💾 Запомнить промпт без генерации",
                "en": "💾 Save the prompt without generating"}),
    ("status", {"ru": "📊 Статус сервера и очереди",
                "en": "📊 Server and queue status"}),
    ("queue", {"ru": "📥 Показать очередь",
               "en": "📥 Show the queue"}),
    ("stop", {"ru": "⏹ Прервать текущую генерацию",
              "en": "⏹ Interrupt the current generation"}),
    ("clearqueue", {"ru": "🗑 Очистить очередь",
                    "en": "🗑 Clear the queue"}),
    ("last", {"ru": "🖼 Прислать последний результат ещё раз",
              "en": "🖼 Resend the last result"}),
    ("regen", {"ru": "🔁 Перегенерировать с новым seed",
               "en": "🔁 Regenerate with a new seed"}),
    ("nodes", {"ru": "🧩 Список нод workflow",
               "en": "🧩 List workflow nodes"}),
    ("params", {"ru": "⚙️ Параметры ноды: /params 57:80",
                "en": "⚙️ Node parameters: /params 57:80"}),
    ("set", {"ru": "✏️ Изменить параметр: /set steps 12",
             "en": "✏️ Set a parameter: /set steps 12"}),
    ("unset", {"ru": "↩️ Сбросить параметр: /unset steps",
               "en": "↩️ Reset a parameter: /unset steps"}),
    ("settings", {"ru": "📋 Текущие переопределения",
                  "en": "📋 Current overrides"}),
    ("reset", {"ru": "🧹 Сбросить все переопределения",
               "en": "🧹 Reset all overrides"}),
    ("steps", {"ru": "⚡ Шаги семплирования", "en": "⚡ Sampling steps"}),
    ("cfg", {"ru": "⚡ CFG", "en": "⚡ CFG"}),
    ("width", {"ru": "⚡ Ширина", "en": "⚡ Width"}),
    ("height", {"ru": "⚡ Высота", "en": "⚡ Height"}),
    ("batch", {"ru": "⚡ Кол-во изображений за раз", "en": "⚡ Images per run"}),
    ("sampler", {"ru": "⚡ Сэмплер", "en": "⚡ Sampler"}),
    ("scheduler", {"ru": "⚡ Планировщик", "en": "⚡ Scheduler"}),
    ("seed", {"ru": "🎲 Seed: /seed 123 | /seed random",
              "en": "🎲 Seed: /seed 123 | /seed random"}),
    ("denoise", {"ru": "⚡ Сила изменения (img2img)", "en": "⚡ Denoise strength (img2img)"}),
    ("cnet", {"ru": "🎛 ControlNet: /cnet on|off|mode|strength",
              "en": "🎛 ControlNet: /cnet on|off|mode|strength"}),
    ("lora", {"ru": "🧩 LoRA: /lora list|имя|off", "en": "🧩 LoRA: /lora list|name|off"}),
    ("workflow", {"ru": "🧩 Сменить workflow: /workflow img2img",
                  "en": "🧩 Switch workflow: /workflow img2img"}),
    ("model", {"ru": "🧠 Сменить модель: /model имя",
               "en": "🧠 Switch model: /model name"}),
    ("models", {"ru": "🧠 Список доступных моделей",
                "en": "🧠 List available models"}),
    ("users", {"ru": "👥 Пользователи бота (админ)",
               "en": "👥 Bot users (admin)"}),
    ("adduser", {"ru": "➕ Дать доступ: /adduser ID (админ)",
                 "en": "➕ Grant access: /adduser ID (admin)"}),
    ("deluser", {"ru": "➖ Забрать доступ: /deluser ID (админ)",
                 "en": "➖ Revoke access: /deluser ID (admin)"}),
    ("id", {"ru": "🆔 Показать свой ID", "en": "🆔 Show your ID"}),
    ("lang", {"ru": "🌐 Язык бота для этого чата",
              "en": "🌐 Bot language for this chat"}),
    ("help", {"ru": "❓ Полная справка", "en": "❓ Full help"}),
]

STRINGS = {
    "ru": {
        # access / plumbing
        "deny_private": "⛔ Доступ запрещён. Твой ID: {user_id} — админ может добавить его командой /adduser {user_id}.",
        "deny_private_short": "⛔ Доступ запрещён.",
        "not_a_command": "Я понимаю только команды. Напиши /generate <описание> или /help.",
        "unknown_command": "❓ Неизвестная команда /{cmd}. Полный список: /help",
        "admin_only": "⛔ Эта команда только для админов бота.",
        "internal_error": "⚠️ Внутренняя ошибка обработки команды, подробности в логах сервера.",
        "id_reply": "🆔 Твой ID: {user_id}\nID этого чата: {chat_id}",
        # start / help
        "start_text": "Привет! Я бот твоего ComfyUI.\nБыстрый старт: /generate кот-космонавт\nВсе команды: /help",
        "help_text": (
            "<b>Генерация</b>\n"
            "/generate &lt;текст&gt; — сгенерировать изображение\n"
            "/generate &lt;текст&gt; + картинка — img2img: пришли фото с подписью /generate или ответь на фото\n"
            "/workflow — список и смена workflow (txt2img / img2img)\n"
            "/prompt &lt;текст&gt; — запомнить промпт на будущее\n"
            "/regen — перегенерировать последний промпт с новым seed\n"
            "/last — прислать последний результат ещё раз\n\n"
            "<b>Параметры workflow</b>\n"
            "/nodes — список нод\n"
            "/params &lt;нода&gt; — параметры ноды и их значения\n"
            "/set &lt;нода&gt;.&lt;параметр&gt; &lt;значение&gt; — изменить параметр\n"
            "/set &lt;параметр&gt; &lt;значение&gt; — если параметр уникален\n"
            "/unset &lt;нода&gt;.&lt;параметр&gt; — сбросить один параметр\n"
            "/settings — что переопределено\n"
            "/reset — сбросить всё\n\n"
            "<b>Быстрые параметры</b>\n"
            "/steps 8 · /cfg 1 · /width 1024 · /height 1720 · /batch 4\n"
            "/sampler res_multistep · /scheduler simple\n"
            "/seed 123 | /seed random\n"
            "/denoise 0.65 — сила изменения в img2img\n"
            "/cnet — ControlNet для img2img: on|off, mode, strength\n"
            "/lora — LoRA для обоих флоу: list|имя|strength|off\n"
            "/models и /model &lt;имя&gt; — смена модели\n\n"
            "<b>Сервер</b>\n"
            "/status · /queue · /stop · /clearqueue\n\n"
            "<b>Пользователи</b>\n"
            "/id — показать свой ID (доступно всем)\n"
            "/users — список пользователей (админ)\n"
            "/adduser &lt;ID&gt; — дать доступ (админ); можно ответом на сообщение\n"
            "/deluser &lt;ID&gt; — забрать доступ (админ)\n"
            "/lang — язык бота для этого чата\n\n"
            "Ноду можно указывать ID-ом («57:80»), классом или частью названия."
        ),
        # language
        "lang_current": "🌐 Язык этого чата: {lang}",
        "lang_available": "Доступные языки: {langs}",
        "lang_usage": "Сменить: /lang ru или /lang en",
        "lang_unknown": "Не знаю язык «{lang}». {available}",
        "lang_set": "🌐 Язык чата изменён: {lang}",
        "lang_group_admin_only": "⛔ В групповом чате язык меняют только админы.",
        # generation
        "usage_generate": "Использование: /generate описание изображения",
        "workflow_usage": "🧩 Текущий workflow: {name}\nДоступные: {list}\nСменить: /workflow <имя>",
        "workflow_set": "🧩 Workflow переключён: {name}",
        "workflow_denoise_hint": "🎚 Сила изменения исходного фото: /denoise 0.65 (меньше — бережнее правки)",
        "workflow_unknown": "Не знаю workflow «{name}».\nДоступные: {list}",
        "img_need": "🖼 Workflow «{name}» генерирует по изображению: пришли картинку (или ответь ею на сообщение) вместе с /generate <описание>.",
        "img_unused": "⚠️ Изображение не используется: активный workflow «{name}» не принимает картинки. Смени его: /workflow img2img",
        "img_upload_fail": "⚠️ Не удалось загрузить изображение в ComfyUI.",
        "cnet_status": "🎛 ControlNet: {state} · режим: {mode} · сила: {strength}\nКонтрольная маска: {image}\nПрименяется к текущему workflow («{name}»). Команды: /cnet on|off · /cnet mode <имя> · /cnet mode list · /cnet strength 0.8 · /cnet clear · фото с подписью /cnet — загрузить референс.",
        "cnet_on": "✅ ControlNet включён — применяется к текущему workflow «{name}».",
        "cnet_on_no_model": "✅ ControlNet включён для «{name}», но модель не найдена — скачай Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors (~6.7 ГБ) в models/model_patches/",
        "cnet_off": "⛔ ControlNet выключен.",
        "cnet_mode_set": "🎛 Режим (препроцессор): {name}",
        "cnet_mode_cleared": "Режим сброшен — контрольная картинка идёт как есть.",
        "cnet_mode_none": "нет (сырое фото)",
        "cnet_mode_missing": "Препроцессор «{name}» не найден. Доступные: {list}",
        "cnet_modes_empty": "Препроцессоры недоступны — нужен пак comfyui_controlnet_aux.",
        "cnet_mode_list": "🎛 Доступные режимы (выбор: /cnet mode <имя>):\n{list}",
        "cnet_strength_set": "🎚 Сила ControlNet: {value}",
        "cnet_patch_missing": "⚠️ Модель ControlNet не найдена. Скачай Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors (~6.7 ГБ) в папку models/model_patches/ — huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1",
        "cnet_image_set": "🖼 Контрольная картинка задана для следующей генерации.",
        "cnet_image_cleared": "🗑 Маска сброшена — загрузи референс заново (фото с подписью /cnet).",
        "cnet_image_yes": "задана ✅",
        "cnet_image_no": "не задана",
        "cnet_mask_preparing": "⏳ Готовлю маску из референса…",
        "cnet_mask_ready": "🖼 Маска готова ({mode}). Использовать её в генерациях до сброса /cnet clear?",
        "cnet_mask_approved": "✅ Маска сохранена — ControlNet будет использовать её до /cnet clear.",
        "cnet_mask_approved_short": "Маска сохранена ✅",
        "cnet_mask_cancelled": "Маска отклонена. Загрузи другой референс (фото с /cnet).",
        "cnet_mask_cancelled_short": "Отменено",
        "cnet_no_pending_msg": "Нет маски на одобрении",
        "cnet_need_reference": "⚠️ ControlNet включён, но маска не задана: пришли фото с подписью /cnet — бот подготовит маску на одобрение.",
        "cnet_mask_lost": "⚠️ Маска больше недоступна в ComfyUI (папка input очищена). Загрузи референс заново: фото с подписью /cnet.",
        "cnet_mask_failed": "⚠️ Не удалось подготовить маску: {reason}",
        "cnet_mask_timeout": "⚠️ Не успел подготовить маску за 5 минут — первый запуск препроцессора качает веса модели. Попробуй ещё раз.",
        "cnet_mask_remake_hint": "Новая маска применится к референсам, загруженным после смены режима. Текущая маска сохранена до /cnet clear.",
        "cnet_btn_use": "✅ Использовать",
        "cnet_btn_cancel": "✖️ Отмена",
        "cnet_need_img2img": "⚠️ Не смог встроить ControlNet в этот workflow (нет сэмплера/VAE).",
        "cnet_strength_bad": "Нужно число, например: /cnet strength 0.8",
        "cnet_group_admin_only": "⛔ В групповом чате ControlNet меняют только админы.",
        "cnet_unknown": "Не понял подкоманду «{sub}». Команды: /cnet on|off|mode|strength|clear",
        "lora_status": "🧩 LoRA: {name} · сила: {strength}\nПрименяется к текущему workflow («{name2}»). Команды: /lora list · /lora <имя> · /lora strength 0.8 · /lora off",
        "lora_none": "нет",
        "lora_usage": "🧩 LoRA: {name} · сила: {strength}\nВыбор: /lora <имя> · список: /lora list · сила: /lora strength 0.8 · выключить: /lora off",
        "lora_set": "🧩 LoRA выбрана: {name} (сила {strength}). Действует до /lora off или смены.",
        "lora_off": "🧩 LoRA выключена.",
        "lora_unknown": "LoRA «{name}» не найдена. Доступные: {list}",
        "lora_strength_set": "🎚 Сила LoRA: {value}",
        "lora_strength_bad": "Нужно число, например: /lora strength 0.8",
        "lora_file_missing": "⚠️ Файл LoRA «{file}» отсутствует в models/loras/ — скачай его и попробуй снова.",
        "lora_need_sampler": "⚠️ Не смог встроить LoRA в этот workflow.",
        "img_dl_failed": "⚠️ Не удалось скачать изображение из Telegram ({reason}). Попробуй ещё раз — подробности в логах сервера.",
        "img_too_large": "⚠️ Файл больше 20 МБ — Telegram не отдаёт такие файлы ботам. Пришли картинку обычным (сжатым) фото.",
        "workflow_missing": "Файл workflow не найден: {path}",
        "no_prompt_node": "Не нашёл в workflow ноду с текстом промпта.",
        "prompt_saved": "💾 Промпт сохранён: «{text}»\nБудет использован при следующей /generate (даже без текста).",
        "usage_prompt": "Использование: /prompt текст промпта",
        "prompt_rejected": "ComfyUI отклонил workflow (HTTP {code}).",
        "prompt_error_line": "Ошибка: {message}",
        "prompt_node_error_line": "Нода {node}: {messages}",
        "unexpected_response": "ComfyUI вернул неожиданный ответ без prompt_id: {resp}",
        "queue_connect_fail": "Не удалось подключиться к ComfyUI.",
        "generating": "⏳ Генерирую…",
        "generating_status": "⏳ Генерирую… {elapsed}с · {detail}",
        "progress_step": "шаг {value}/{max}",
        "progress_eta": "осталось ~{eta}с",
        "place_running": "выполняется",
        "place_queue": "в очереди: {pos}/{total}",
        "place_waiting": "ждёт",
        "job_vanished": "❌ Задача исчезла из очереди — её отменили (/stop, /clearqueue) или ComfyUI перезапустился.",
        "wait_timeout": "⏰ Не дождался результата за {minutes} мин. Попробуй /last позже.",
        "error_no_images": "❌ Генерация упала с ошибкой, подробности в логах ComfyUI.",
        "no_images": "Генерация завершилась, но workflow не сохранил изображений.",
        "done": "✅ Готово за {elapsed}с · изображений: {count}",
        "done_error": "⚠️ Завершено с ошибкой за {elapsed}с · сохранено изображений: {count}",
        "caption_ok": "🎨 {text}",
        "caption_ok_plain": "🎨 Готово",
        "caption_error": "⚠️ Ошибка генерации, частичный результат: {text}",
        "caption_error_plain": "⚠️ Частичный результат",
        "album_partial_fail": "⚠️ Часть изображений могла не отправиться — повтори через /last.",
        "regen_suffix": "(regen 🔁)",
        # nodes / params
        "nodes_title": "🧩 Ноды workflow:",
        "overrides_count": "\n\nПереопределено параметров: {count}. Смотри: /settings",
        "settings_empty": "Пока ничего не переопределено.\nУкажи ноду: /params 57:80 (список: /nodes)",
        "settings_title": "📋 Текущие переопределения:",
        "settings_prompt_line": "промпт: «{text}»",
        "node_not_found": "Нода «{key}» не найдена. Список: /nodes",
        "node_ambiguous": "Под «{key}» подходит несколько нод, уточни ID:\n{list}",
        "param_not_found_anywhere": "Параметр «{param}» не найден ни в одной ноде. См. /nodes и /params.",
        "param_multiple": "Параметр «{param}» есть в нескольких нодах, уточни ноду:\n{list}\nФормат: /set <ID>.{param} <значение>",
        "param_missing": "У ноды «{node}» ({cls}) нет параметра «{param}».\nДоступные: {scalars}",
        "set_usage": "Использование:\n/set <нода>.<параметр> <значение>\n/set <параметр> <значение>\nНапример: /set 57:80.steps 12 или /set steps 8",
        "set_done": "✅ {label}\n{param}: {old} → {new}\nПрименится к следующей /generate",
        "unset_usage": "Использование: /unset <нода>.<параметр> или /unset <параметр>",
        "unset_done_count": "↩️ Сброшено параметров: {count}",
        "unset_none": "Таких переопределений нет — /settings",
        "reset_done": "🧹 Все переопределения сброшены — используется workflow как в файле.",
        "params_header": "⚙️ «{node}» {cls} — «{title}»",
        "overridden_marker": "  ✏️ переопределено",
        "variants_suffix": "  (варианты: {opts})",
        "wires_suffix": "  (входы-связи: {wires})",
        "set_hint": "\nМенять: /set {node}.<параметр> <значение>",
        "usage_shortcut": "Использование: /{cmd} <значение>",
        "value_options": "Допустимые значения: {opts}",
        "value_refine": "Уточни значение «{value}», подходят: {opts}",
        "need_int": "Нужно число (INT).",
        "need_float": "Нужно число (FLOAT).",
        "need_number_bool": "Нужно число ({ptype}), а не true/false.",
        "not_finite": "Нужно конечное число.",
        "out_of_range": "Число вне диапазона ({lo}…{hi}).",
        "need_bool": "Нужно true/false.",
        # seed
        "seed_usage": "Использование: /seed 12345 · /seed random · /seed increment · /seed decrement",
        "seed_not_number": "Нужен номер seed (целое число) или random / increment / decrement.",
        "seed_range": "Seed должен быть от 0 до 18446744073709551615.",
        "seed_no_node": "В workflow нет ноды с параметром seed.",
        "seed_modes_unavailable": "Режимы increment/decrement доступны только при ноде генератора seed (AdvancedSeedGenerator).",
        "seed_set": "🎲 Seed: {what} (нода «{nodes}»)",
        "seed_set_multi": "🎲 Seed: {what} (ноды: «{nodes}»)",
        "seed_random": "случайный при каждой генерации",
        "seed_increment": "инкремент от предыдущего",
        "seed_decrement": "декремент от предыдущего",
        # model
        "model_none": "В workflow нет ноды загрузки модели (UNETLoader/CheckpointLoader).",
        "model_current": "Текущая модель ({param}): {value}\nСписок: /models · Смена: /model <имя>",
        "models_empty": "Не получил список моделей от ComfyUI (/object_info).",
        "models_title": "🧠 Модели ({param}), всего {count}:",
        # status / queue
        "server_no_response": "⚠️ ComfyUI не отвечает на {host}",
        "status_title": "📊 Статус ComfyUI",
        "status_version": "Версия: {version}",
        "status_ram": "RAM: {free} / {total} ГБ свободно",
        "status_gpu": "GPU {name}: {free} / {total} ГБ VRAM свободно",
        "status_queue_line": "Очередь: выполняется {running}, ждёт {pending}",
        "status_overrides_line": "Переопределений: {count}",
        "status_bot_line": "🤖 Бот: аптайм {uptime} · перезапусков полинга: {restarts} · апдейтов обработано: {updates}",
        "queue_empty": "📥 Очередь пуста.",
        "queue_title": "📥 Очередь:",
        "queue_running_item": "  ▶ выполняется: {id}…",
        "queue_pending_item": "  ⏳ ждёт: {id}…",
        "interrupt_ok": "⏹ Сигнал прерывания отправлен.",
        "interrupt_fail": "⚠️ Не удалось связаться с ComfyUI.",
        "clear_ok": "🗑 Очередь очищена (текущая генерация не прервана — см. /stop).",
        "last_none": "Я ещё ничего не генерировал.",
        "last_unavailable": "Изображения последней генерации больше не доступны (история очищена).",
        "last_caption_plain": "🎨 Последний результат",
        "regen_none": "Нет последней генерации для повтора.",
        # users
        "users_title": "👥 Пользователи бота:",
        "users_admin_item": "  👑 {id} (админ)",
        "users_item": "  • {id}",
        "users_footer": "\nДобавить: /adduser <ID> · Удалить: /deluser <ID>\nАдмины задаются только в config.json.",
        "user_id_needed": "Нужен числовой Telegram ID (например /adduser 123456789). Узнать его человек может, написав боту /id в личку или из ответа «Доступ запрещён».",
        "reply_or_id_needed": "Укажи ID (/adduser 123456789) или ответь этой командой на сообщение пользователя.",
        "user_is_admin": "{id} — админ, у него и так полный доступ.",
        "user_already_allowed": "Пользователь {id} уже имеет доступ.",
        "user_added": "✅ Пользователь {id} добавлен — теперь может писать боту.",
        "admin_protected": "👑 Админа нельзя удалить через бота — убери его из списка admins в config.json (нужен перезапуск ComfyUI).",
        "user_not_listed": "Пользователя {id} нет в списке разрешённых.",
        "user_deleted": "➖ Пользователь {id} удалён — доступ закрыт.",
    },
    "en": {
        # access / plumbing
        "deny_private": "⛔ Access denied. Your ID: {user_id} — an admin can add it with /adduser {user_id}.",
        "deny_private_short": "⛔ Access denied.",
        "not_a_command": "I only understand commands. Try /generate <description> or /help.",
        "unknown_command": "❓ Unknown command /{cmd}. Full list: /help",
        "admin_only": "⛔ This command is for bot admins only.",
        "internal_error": "⚠️ Internal error while handling the command, details are in the server logs.",
        "id_reply": "🆔 Your ID: {user_id}\nThis chat's ID: {chat_id}",
        # start / help
        "start_text": "Hi! I'm your ComfyUI bot.\nQuick start: /generate a cat astronaut\nAll commands: /help",
        "help_text": (
            "<b>Generation</b>\n"
            "/generate &lt;text&gt; — generate an image\n"
            "/generate &lt;text&gt; + photo — img2img: attach a photo with the caption /generate, or reply to a photo\n"
            "/workflow — list and switch workflows (txt2img / img2img)\n"
            "/prompt &lt;text&gt; — remember the prompt for later\n"
            "/regen — rerun the last prompt with a new seed\n"
            "/last — resend the last result\n\n"
            "<b>Workflow parameters</b>\n"
            "/nodes — list nodes\n"
            "/params &lt;node&gt; — node parameters and values\n"
            "/set &lt;node&gt;.&lt;param&gt; &lt;value&gt; — change a parameter\n"
            "/set &lt;param&gt; &lt;value&gt; — if the parameter name is unique\n"
            "/unset &lt;node&gt;.&lt;param&gt; — reset one parameter\n"
            "/settings — what is overridden\n"
            "/reset — reset everything\n\n"
            "<b>Quick parameters</b>\n"
            "/steps 8 · /cfg 1 · /width 1024 · /height 1720 · /batch 4\n"
            "/sampler res_multistep · /scheduler simple\n"
            "/seed 123 | /seed random\n"
            "/denoise 0.65 — img2img change strength\n"
            "/cnet — ControlNet for img2img: on|off, mode, strength\n"
            "/lora — LoRA for both flows: list|name|strength|off\n"
            "/models and /model &lt;name&gt; — switch the model\n\n"
            "<b>Server</b>\n"
            "/status · /queue · /stop · /clearqueue\n\n"
            "<b>Users</b>\n"
            "/id — show your ID (everyone)\n"
            "/users — list users (admin)\n"
            "/adduser &lt;ID&gt; — grant access (admin); or reply to their message\n"
            "/deluser &lt;ID&gt; — revoke access (admin)\n"
            "/lang — bot language for this chat\n\n"
            "A node can be referenced by ID («57:80»), by class or by part of its name."
        ),
        # language
        "lang_current": "🌐 Language of this chat: {lang}",
        "lang_available": "Available languages: {langs}",
        "lang_usage": "To change: /lang ru or /lang en",
        "lang_unknown": "I don't know «{lang}». {available}",
        "lang_set": "🌐 Chat language changed: {lang}",
        "lang_group_admin_only": "⛔ In group chats only admins can change the language.",
        # generation
        "usage_generate": "Usage: /generate image description",
        "workflow_usage": "🧩 Current workflow: {name}\nAvailable: {list}\nSwitch with: /workflow <name>",
        "workflow_set": "🧩 Workflow switched: {name}",
        "workflow_denoise_hint": "🎚 How strongly the source photo is changed: /denoise 0.65 (lower = subtler edits)",
        "workflow_unknown": "Unknown workflow «{name}».\nAvailable: {list}",
        "img_need": "🖼 Workflow «{name}» works from an image: attach a photo (or reply to a message with one) together with /generate <description>.",
        "img_unused": "⚠️ The image won't be used: the active workflow «{name}» doesn't accept images. Switch with: /workflow img2img",
        "img_upload_fail": "⚠️ Failed to upload the image to ComfyUI.",
        "cnet_status": "🎛 ControlNet: {state} · mode: {mode} · strength: {strength}\nControl mask: {image}\nApplies to the current workflow («{name}»). Commands: /cnet on|off · /cnet mode <name> · /cnet mode list · /cnet strength 0.8 · /cnet clear · a photo with the /cnet caption uploads a reference.",
        "cnet_on": "✅ ControlNet enabled — applies to the current workflow «{name}».",
        "cnet_on_no_model": "✅ ControlNet enabled, but the model is missing — download Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors (~6.7 GB) into models/model_patches/",
        "cnet_off": "⛔ ControlNet disabled.",
        "cnet_mode_set": "🎛 Mode (preprocessor): {name}",
        "cnet_mode_cleared": "Mode cleared — the control image is used as-is.",
        "cnet_mode_none": "none (raw photo)",
        "cnet_mode_missing": "Preprocessor «{name}» not found. Available: {list}",
        "cnet_modes_empty": "Preprocessors unavailable — the comfyui_controlnet_aux pack is required.",
        "cnet_mode_list": "🎛 Available modes (pick one: /cnet mode <name>):\n{list}",
        "cnet_strength_set": "🎚 ControlNet strength: {value}",
        "cnet_patch_missing": "⚠️ ControlNet model not found. Download Z-Image-Turbo-Fun-Controlnet-Union-2.1.safetensors (~6.7 GB) into models/model_patches/ — huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1",
        "cnet_image_set": "🖼 Control image set for the next generation.",
        "cnet_image_cleared": "🗑 Mask cleared — upload a new reference (photo with the /cnet caption).",
        "cnet_image_yes": "set ✅",
        "cnet_image_no": "not set",
        "cnet_mask_preparing": "⏳ Preparing the mask from the reference…",
        "cnet_mask_ready": "🖼 Mask ready ({mode}). Use it for generations until /cnet clear?",
        "cnet_mask_approved": "✅ Mask saved — ControlNet will use it until /cnet clear.",
        "cnet_mask_approved_short": "Mask saved ✅",
        "cnet_mask_cancelled": "Mask rejected. Upload another reference (photo with /cnet).",
        "cnet_mask_cancelled_short": "Cancelled",
        "cnet_no_pending_msg": "No mask pending approval",
        "cnet_need_reference": "⚠️ ControlNet is enabled but no mask is set: send a photo with the /cnet caption — the bot will prepare a mask for approval.",
        "cnet_mask_lost": "⚠️ The mask is no longer available in ComfyUI (input folder cleared). Upload the reference again: photo with /cnet.",
        "cnet_mask_failed": "⚠️ Failed to prepare the mask: {reason}",
        "cnet_mask_timeout": "⚠️ Couldn't prepare the mask within 5 minutes — the preprocessor downloads its weights on first run. Try again.",
        "cnet_mask_remake_hint": "The new mode applies to references uploaded after the change. The current mask is kept until /cnet clear.",
        "cnet_btn_use": "✅ Use",
        "cnet_btn_cancel": "✖️ Cancel",
        "cnet_need_img2img": "⚠️ Couldn't wire ControlNet into this workflow (no sampler/VAE).",
        "cnet_strength_bad": "Expected a number, e.g.: /cnet strength 0.8",
        "cnet_group_admin_only": "⛔ In group chats only admins can change ControlNet.",
        "cnet_unknown": "Didn't understand subcommand «{sub}». Commands: /cnet on|off|mode|strength|clear",
        "lora_status": "🧩 LoRA: {name} · strength: {strength}\nApplies to the current workflow («{name2}»). Commands: /lora list · /lora <name> · /lora strength 0.8 · /lora off",
        "lora_none": "none",
        "lora_usage": "🧩 LoRA: {name} · strength: {strength}\nPick: /lora <name> · list: /lora list · strength: /lora strength 0.8 · disable: /lora off",
        "lora_set": "🧩 LoRA selected: {name} (strength {strength}). Active until /lora off or a change.",
        "lora_off": "🧩 LoRA disabled.",
        "lora_unknown": "LoRA «{name}» not found. Available: {list}",
        "lora_strength_set": "🎚 LoRA strength: {value}",
        "lora_strength_bad": "Expected a number, e.g.: /lora strength 0.8",
        "lora_file_missing": "⚠️ LoRA file «{file}» is missing from models/loras/ — download it and try again.",
        "lora_need_sampler": "⚠️ Couldn't wire LoRA into this workflow.",
        "img_dl_failed": "⚠️ Failed to download the image from Telegram ({reason}). Try again — details are in the server logs.",
        "img_too_large": "⚠️ The file is over 20 MB — Telegram won't deliver it to bots. Send it as a regular (compressed) photo.",
        "workflow_missing": "Workflow file not found: {path}",
        "no_prompt_node": "Couldn't find a prompt text node in the workflow.",
        "prompt_saved": "💾 Prompt saved: «{text}»\nIt will be used by the next /generate (even without text).",
        "usage_prompt": "Usage: /prompt prompt text",
        "prompt_rejected": "ComfyUI rejected the workflow (HTTP {code}).",
        "prompt_error_line": "Error: {message}",
        "prompt_node_error_line": "Node {node}: {messages}",
        "unexpected_response": "ComfyUI returned an unexpected response without prompt_id: {resp}",
        "queue_connect_fail": "Couldn't connect to ComfyUI.",
        "generating": "⏳ Generating…",
        "generating_status": "⏳ Generating… {elapsed}s · {detail}",
        "progress_step": "step {value}/{max}",
        "progress_eta": "~{eta}s left",
        "place_running": "running",
        "place_queue": "in queue: {pos}/{total}",
        "place_waiting": "waiting",
        "job_vanished": "❌ The job disappeared from the queue — it was cancelled (/stop, /clearqueue) or ComfyUI restarted.",
        "wait_timeout": "⏰ No result after {minutes} min. Try /last later.",
        "error_no_images": "❌ Generation failed with an error, details are in the ComfyUI logs.",
        "no_images": "Generation finished, but the workflow saved no images.",
        "done": "✅ Done in {elapsed}s · images: {count}",
        "done_error": "⚠️ Finished with an error in {elapsed}s · images saved: {count}",
        "caption_ok": "🎨 {text}",
        "caption_ok_plain": "🎨 Done",
        "caption_error": "⚠️ Generation error, partial result: {text}",
        "caption_error_plain": "⚠️ Partial result",
        "album_partial_fail": "⚠️ Some images may not have been sent — try /last again.",
        "regen_suffix": "(regen 🔁)",
        # nodes / params
        "nodes_title": "🧩 Workflow nodes:",
        "overrides_count": "\n\nParameters overridden: {count}. See: /settings",
        "settings_empty": "Nothing is overridden yet.\nPick a node: /params 57:80 (list: /nodes)",
        "settings_title": "📋 Current overrides:",
        "settings_prompt_line": "prompt: «{text}»",
        "node_not_found": "Node «{key}» not found. List: /nodes",
        "node_ambiguous": "Several nodes match «{key}», specify the ID:\n{list}",
        "param_not_found_anywhere": "Parameter «{param}» was not found in any node. See /nodes and /params.",
        "param_multiple": "Parameter «{param}» exists in several nodes, pick one:\n{list}\nFormat: /set <ID>.{param} <value>",
        "param_missing": "Node «{node}» ({cls}) has no parameter «{param}».\nAvailable: {scalars}",
        "set_usage": "Usage:\n/set <node>.<param> <value>\n/set <param> <value>\nExample: /set 57:80.steps 12 or /set steps 8",
        "set_done": "✅ {label}\n{param}: {old} → {new}\nApplies to the next /generate",
        "unset_usage": "Usage: /unset <node>.<param> or /unset <param>",
        "unset_done_count": "↩️ Parameters reset: {count}",
        "unset_none": "No such overrides — /settings",
        "reset_done": "🧹 All overrides cleared — the workflow is used as saved in the file.",
        "params_header": "⚙️ «{node}» {cls} — «{title}»",
        "overridden_marker": "  ✏️ overridden",
        "variants_suffix": "  (options: {opts})",
        "wires_suffix": "  (wired inputs: {wires})",
        "set_hint": "\nChange with: /set {node}.<param> <value>",
        "usage_shortcut": "Usage: /{cmd} <value>",
        "value_options": "Allowed values: {opts}",
        "value_refine": "Refine «{value}», matches: {opts}",
        "need_int": "Expected an integer (INT).",
        "need_float": "Expected a number (FLOAT).",
        "need_number_bool": "Expected a number ({ptype}), not true/false.",
        "not_finite": "Expected a finite number.",
        "out_of_range": "Number out of range ({lo}…{hi}).",
        "need_bool": "Expected true/false.",
        # seed
        "seed_usage": "Usage: /seed 12345 · /seed random · /seed increment · /seed decrement",
        "seed_not_number": "Expected a seed number (integer) or random / increment / decrement.",
        "seed_range": "Seed must be between 0 and 18446744073709551615.",
        "seed_no_node": "The workflow has no node with a seed parameter.",
        "seed_modes_unavailable": "increment/decrement modes require a seed generator node (AdvancedSeedGenerator).",
        "seed_set": "🎲 Seed: {what} (node \"{nodes}\")",
        "seed_set_multi": "🎲 Seed: {what} (nodes: \"{nodes}\")",
        "seed_random": "random on every generation",
        "seed_increment": "incremented from the previous one",
        "seed_decrement": "decremented from the previous one",
        # model
        "model_none": "The workflow has no model loader node (UNETLoader/CheckpointLoader).",
        "model_current": "Current model ({param}): {value}\nList: /models · Switch: /model <name>",
        "models_empty": "Couldn't get the model list from ComfyUI (/object_info).",
        "models_title": "🧠 Models ({param}), {count} total:",
        # status / queue
        "server_no_response": "⚠️ ComfyUI is not responding at {host}",
        "status_title": "📊 ComfyUI status",
        "status_version": "Version: {version}",
        "status_ram": "RAM: {free} / {total} GB free",
        "status_gpu": "GPU {name}: {free} / {total} GB VRAM free",
        "status_queue_line": "Queue: {running} running, {pending} waiting",
        "status_overrides_line": "Overrides: {count}",
        "status_bot_line": "🤖 Bot: uptime {uptime} · polling restarts: {restarts} · updates processed: {updates}",
        "queue_empty": "📥 The queue is empty.",
        "queue_title": "📥 Queue:",
        "queue_running_item": "  ▶ running: {id}…",
        "queue_pending_item": "  ⏳ waiting: {id}…",
        "interrupt_ok": "⏹ Interrupt signal sent.",
        "interrupt_fail": "⚠️ Couldn't reach ComfyUI.",
        "clear_ok": "🗑 Queue cleared (the running generation is not interrupted — see /stop).",
        "last_none": "I haven't generated anything yet.",
        "last_unavailable": "The images from the last generation are no longer available (history cleared).",
        "last_caption_plain": "🎨 Last result",
        "regen_none": "No previous generation to repeat.",
        # users
        "users_title": "👥 Bot users:",
        "users_admin_item": "  👑 {id} (admin)",
        "users_item": "  • {id}",
        "users_footer": "\nAdd: /adduser <ID> · Remove: /deluser <ID>\nAdmins are set only in config.json.",
        "user_id_needed": "A numeric Telegram ID is required (e.g. /adduser 123456789). A person can learn their ID by sending /id to the bot in a private chat or from the «Access denied» reply.",
        "reply_or_id_needed": "Provide an ID (/adduser 123456789) or reply with this command to a message from the user.",
        "user_is_admin": "{id} is an admin and already has full access.",
        "user_already_allowed": "User {id} already has access.",
        "user_added": "✅ User {id} added — they can now talk to the bot.",
        "admin_protected": "👑 An admin can't be removed via the bot — remove them from the admins list in config.json (requires a ComfyUI restart).",
        "user_not_listed": "User {id} is not on the allowed list.",
        "user_deleted": "➖ User {id} removed — access revoked.",
    },
}
