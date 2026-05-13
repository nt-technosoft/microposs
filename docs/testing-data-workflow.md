# Test Data Workflow

Цель тестового заполнения базы — не перенести Excel-итоги в таблицы, а быстро
проиграть тот же жизненный цикл, который проходит владелец бизнеса в интерфейсе.
Только так совпадение цифр можно считать проверкой логики, а не проверкой
импортёра.

## Что считается правильной симуляцией

Тестовый сценарий должен идти через те же доменные входы, что и UI:

1. Создать пользователей, бизнес, склады, кассы, инвесторов и справочники.
2. Создать товары и категории через catalog/service или API.
3. Создать инвестдоговор или партнёрский приход через procurement/agreement flow.
4. Внести капитал, оплатить товары и расходы через штатные операции.
5. Оприходовать товар через `receive_procurement`, включая partial receive и batch
   allocation, если в реальном кейсе товар приходит партиями.
6. Переместить товар со склада в магазин через `transfer_lot_stock`.
7. Открыть POS-смену в магазине.
8. Создать продажи через `create_sale` с тем же payload-смыслом, который отправляет
   frontend.
9. Закрыть смены, выполнить возвраты, обмен валют, выплаты прибыли и погашения
   долгов только через доменные сервисы/API.
10. Сравнить отчёты, сверку, инвесторский кабинет и аудит продаж с ожидаемыми
    Excel-цифрами.

## Что нельзя считать доказательством корректности

- Вставить уже готовые Excel-итоги в отчётные таблицы.
- Создать `Lot`, `Sale`, `JournalEntry`, `CashEntry` прямым ORM-кодом в обход
  сервисов.
- Подставить данные, которые невозможно создать из UI/API.
- Автоматически менять склад продажи, если в Excel указан другой склад.
- Автоматически “доливать” деньги в кассу без явной операции, если этот шаг влияет
  на проверяемую финансовую картину.
- Пропускать продажи из-за нехватки остатков и считать сценарий полным.

## Актуальный Excel workflow

Для E07 этот workflow остаётся каноничным партнёрским replay, но не должен
считаться единственным доказательством новой procurement-архитектуры. После E07
нужно дополнительно покрывать own-funds, deferred/installment/consignment и
blocked hybrid сценарии отдельными smoke/test seed flows.

Старые команды прямого Excel-import удалены. Каноничный путь сейчас один:

1. `excel_snapshot_from_xlsx` — преобразует исходный `.xlsx` в JSON snapshot.
2. `excel_workflow_staged` — поэтапно проигрывает жизненный цикл владельца:
   baseline → procurements → transfers → sales → final.
3. `excel_workflow_audit` — тот же сценарий одной командой для быстрой
   регрессии после того, как staged-проход уже проверен руками.

Этот workflow не импортирует готовые отчётные итоги. Он создаёт пользователей,
товары, партнёрские приходы, partial receive, перемещения, POS-смены и продажи
через доменные сервисы, максимально близкие к UI/API.

## Текущая команда

Каноничный источник Excel-кейса лежит в корне проекта:

```text
MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx
```

Из него собран текущий snapshot:

```text
backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json
```

Если Excel-файл изменился, snapshot пересобирается так:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_snapshot_from_xlsx \
  --source-xlsx "MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx" \
  --output-json backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json
```

Полный workflow seed доступен как management command:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_audit --dry-run
```

`--dry-run` только строит план и показывает предупреждения. Базу он не меняет.

В `DEBUG=False` Excel/demo команды защищены production guard-ом. Для stage/prod
их нельзя запускать случайно: нужен отдельный confirm-флаг, и перед этим должно
быть явное решение очистить или изменить базу.

Применение намеренно сделано разрушительным и требует явного флага:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_audit --apply --wipe
```

После `--apply --wipe` команда создаёт чистую базу для проверки: пользователей,
две пары `owner/investor`, товары, два партнёрских прихода, partial receive,
перемещения в магазин и продажи из Excel через доменные сервисы.

Для ручного аудита основной путь — staged-команда:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage baseline --dry-run
```

Этапы запускаются последовательно:

```bash
# 1. Очистить базу и создать пользователей, бизнесы, справочники, товары
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage baseline --apply --wipe

# 2. Создать два партнёрских прихода и частично оприходовать первую партию
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage procurements --apply

# 3. Переместить товар со склада в магазин
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage transfers --apply

# 4. Проиграть продажи из Excel через POS-сервисы
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage sales --apply

# 5. Обновить агрегаты и вывести финальную сводку
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage final --apply
```
