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

## Текущий статус старого Excel seed

`backend/apps/core/management/commands/seed_from_excel.py` частично подходит для
smoke/reconciliation dataset: он использует `open_procurement`,
`receive_procurement`, `transfer_lot_stock`, `open_pos_session`, `create_sale`,
`exchange_currency`, `pay_dividend`.

Но это не полноценная имитация UI-flow:

- часть master/baseline данных создаётся прямым ORM, что допустимо только для
  начального окружения;
- закупка в старом seed принимается одной партией, без нового partial receive
  сценария;
- растаможка проводится как отдельный операционный расход, а не как targeted
  procurement expense;
- есть fallback-перемещения и смена склада продажи при нехватке остатка;
- кассы иногда “праймятся” owner contribution, чтобы операция прошла;
- старый seed может пропускать строки продаж, если остатка не хватает.

Поэтому его результат нельзя использовать как финальное доказательство, что
пользовательский workflow работает полностью.

## Принцип следующего seed-аудита

Новый сценарий для Excel-кейса должен быть отдельным workflow/audit seed:

- сначала dry-run: показать, какие Excel-строки будут превращены в какие UI/API
  действия;
- затем apply: выполнить действия через сервисы, максимально близкие к API;
- если нужна подготовительная операция, она должна быть явной в отчёте сценария;
- если строка Excel не может быть проиграна корректно, сценарий должен падать или
  фиксировать blocker, а не молча подбирать склад/кассу;
- итоговый отчёт должен показывать:
  - сколько действий выполнено;
  - какие строки Excel не проиграны;
  - какие цифры совпали/не совпали;
  - какие расхождения являются бизнес-расхождениями, а какие техническими.

Такой seed можно считать ускоренной имитацией работы владельца бизнеса, а не
ручным импортом итоговой отчётности.

## Текущая команда

Каноничный источник Excel-кейса лежит в корне проекта:

```text
MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx
```

Из него собран текущий snapshot:

```text
backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json
```

Полный workflow seed всё ещё доступен как management command:

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
