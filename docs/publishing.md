# Публикация в ComfyUI Registry

Плагин публикуется в [registry.comfy.org](https://registry.comfy.org) через GitHub Action
(`.github/workflows/publish.yml`, официальный `Comfy-Org/publish-node-action`).
Action срабатывает на пуш тегов и на ручной запуск (workflow_dispatch).

## Разовая настройка (делается один раз)

1. **Зарегистрировать паблишера**: зайти на [registry.comfy.org](https://registry.comfy.org)
   под своим GitHub-аккаунтом → создать паблишера с ID `xylogenw376dq`
   (или любым другим — тогда поправь `PublisherId` в `pyproject.toml`).
2. **Создать API-ключ** на странице паблишера в реестре.
3. **Добавить секрет** в репозитории: Settings → Secrets and variables → Actions →
   `REGISTRY_ACCESS_TOKEN` = ключ из шага 2.

## Как выпустить новую версию

1. Поднять `version` в `pyproject.toml` (версия должна увеличиваться).
2. Закоммитить и поставить тег:
   ```
   git tag v2.0.1
   git push origin v2.0.1
   ```
3. Action опубликует ноду в реестре; проверить: вкладка Actions репозитория
   и страница паблишера на registry.comfy.org.

После публикации плагин устанавливается из ComfyUI-Manager (Custom Nodes Manager)
по имени `comfyui-controlbot` (паблишер `xylogenw376dq`).
