# ML Clan — Собесы

Сайт-читалка Obsidian-волта с подготовкой к ML-собеседованиям: пулы вопросов,
разборы лайвкодинга, датированные заметки по интервью, материалы и интерактивный
**навигатор вопросов** (фильтры по компаниям/секторам/темам).

Статический сайт собирается из `Собесы/` скриптом `build.py` и отдаётся за
HTTP Basic Auth лёгким Flask-сервером (`server.py`). Деплой — Railway.

## Структура

```
Собесы/            исходный Obsidian-волт (source of truth)
assets/            исходники фронта: style.css, app.js, navigator.js, view.css
build.py           генератор статики -> site/
server.py          Flask + Basic Auth, отдаёт site/
site/              СОБИРАЕТСЯ (в .gitignore), не коммитим
requirements.txt   зависимости
Procfile / railway.json  конфиг деплоя Railway
```

## Что делает `build.py`

- парсит YAML-frontmatter и отбрасывает его;
- конвертит Obsidian-callouts (`> [!question|quote|info|note]`) в стилизованные блоки
  (collapsible `-`/`+` → `<details>`);
- резолвит `[[wikilinks]]`, `[[Имя|Алиас]]`, `[[Папка/Имя]]` и ссылки на `.pdf`
  (нормализация NFC — иначе «й»/«ё» в путях macOS ломают матч); битые ссылки
  превращаются в обычный текст;
- разворачивает эмбеды `![[Заметка]]` (транслюзии) в их содержимое;
- конвертит Obsidian-инлайн: `==хайлайт==` → `<mark>`, `~~зачёркнутое~~` → `<del>`;
- заменяет `dataviewjs`-блок навигатора на standalone-виджет (`navigator.js` +
  `navigator-data.json`), а сам навигатор делает главной страницей (`index.html`);
- **чистит Obsidian-мусор** для «продуктового» вида: пустые окна тренажёра
  (`**Твой ответ:**` + `<br>`-дыры), telegram-id хвосты (`— #id`, `Interview/Source: #id`,
  `Источник: #id`), приватные `t.me/c/...` ссылки, служебные заметки и онбординг
  (`EXCLUDE_RELPATHS`);
- подсвечивает код через Pygments;
- строит боковое дерево-навигацию с человеческими названиями разделов
  (`FOLDER_META`) и клиентский полнотекстовый поиск (`search-index.json`).

## Локальный запуск

```bash
pip install -r requirements.txt
python build.py          # собрать site/
python server.py         # http://localhost:8000  (пароль по умолчанию mlclan, логин любой)
```

Доступ закрыт HTTP Basic Auth. Проверяется только пароль `SITE_PASS` — логин
можно вводить любой (общий пароль для всех). Если задать ещё и `SITE_USER`, то
будет сверяться и логин:

```bash
SITE_PASS=secret python server.py              # логин любой, пароль secret
SITE_USER=vadim SITE_PASS=secret python server.py  # нужны и логин, и пароль
```

## Деплой на Railway

1. Запушить репозиторий на GitHub (`origin/main`).
2. В нужном Railway-проекте: **New → GitHub Repo → mlsobes**.
3. В переменных сервиса задать `SITE_PASS` — общий пароль (иначе дефолт `mlclan`).
   Логин спрашивается браузером, но не проверяется (вводить можно любой). Хочешь
   закрыть ещё и по логину — задай `SITE_USER`.
4. Railway сам поднимет домен; при каждом push в `main` будет пересобирать сайт.

## Обновление контента

Правишь заметки в `Собесы/` (хоть прямо в Obsidian) → коммит → push. Railway
пересоберёт `site/` на деплое. Данные навигатора (`navigator-data.json`)
обновляются отдельно скриптом `Собесы/ML Clan — навигатор/scripts/build_navigator.py`
из исходного экспорта (см. README внутри той папки).
