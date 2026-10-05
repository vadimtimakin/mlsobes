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
  (нормализация NFC — иначе «й»/«ё» в путях macOS ломают матч);
- заменяет `dataviewjs`-блок навигатора на standalone-виджет (`navigator.js` +
  `navigator-data.json`);
- подсвечивает код через Pygments;
- строит боковое дерево-навигацию и клиентский полнотекстовый поиск
  (`search-index.json`).

## Локальный запуск

```bash
pip install -r requirements.txt
python build.py          # собрать site/
python server.py         # http://localhost:8000  (логин/пароль mlclan/mlclan)
```

Логин/пароль задаются переменными `SITE_USER` / `SITE_PASS`:

```bash
SITE_USER=vadim SITE_PASS=secret python server.py
```

## Деплой на Railway

1. Запушить репозиторий на GitHub (`origin/main`).
2. В нужном Railway-проекте: **New → GitHub Repo → mlsobes**.
3. В переменных сервиса задать `SITE_USER` и `SITE_PASS` (обязательно — иначе
   дефолт `mlclan/mlclan`).
4. Railway сам поднимет домен; при каждом push в `main` будет пересобирать сайт.

## Обновление контента

Правишь заметки в `Собесы/` (хоть прямо в Obsidian) → коммит → push. Railway
пересоберёт `site/` на деплое. Данные навигатора (`navigator-data.json`)
обновляются отдельно скриптом `Собесы/ML Clan — навигатор/scripts/build_navigator.py`
из исходного экспорта (см. README внутри той папки).
