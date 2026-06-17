# E99 — Execution Layer Smoke Test — MANIFEST

> Одноразовый полигон. Всё под `sandbox/exec-smoke/`. Сносится в Фазе 7.

Планируемые артефакты по фазам:

## Фаза 1 — Bootstrap (rule 2 — self)
- `MANIFEST.md` — этот файл

## Фаза 2 — data via fresh subagent (rule 3)
- `data/cities.json` — 5 городов (имя + условное население)
- `data/notes.md` — 3–4 строки произвольного текста

## Фаза 3 — скрипт + верификация прогоном (self/subagent + verify)
- `scripts/wordcount.py` — счётчик слов в `data/notes.md`
- `out/wordcount.txt` — сохранённый вывод реального прогона

## Фаза 4 — независимое ревью через Codex (rule 6)
- `reviews/codex-review.md` — вердикт Codex по `scripts/wordcount.py`

## Фаза 5 — параллельный fan-out (rule 3 + параллелизм)
- `parts/a.md`, `parts/b.md`, `parts/c.md` — по строке, 3 параллельных субагента

## Фаза 6 — агрегация + аудит
- `AUDIT.md` — чек-лист наличия+непустоты артефактов фаз 1–5
