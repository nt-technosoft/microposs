# E07 — Procurement Workspace Unification

> **Reference / pre-reset UI context.**
>
> This document was written while the plan was to unify the old `IntakeCreate`
> and `IntakeDetail` flows. After the 2026-05-13 decision, frontend follows
> **controlled radical reset**: build a new `ProcurementWorkspace` and use old
> intake screens only as reference.
>
> Active entrypoint: [`E07-procurement-workspace.md`](./E07-procurement-workspace.md).
> Active reset plan: [`E07-controlled-radical-reset.md`](./E07-controlled-radical-reset.md).
>
> Use this file only for UX principles and edge cases. Do not treat it as the
> active frontend implementation roadmap.
>
> Known risk: this pre-reset document discusses old "source/type/terms" ordering
> and can conflict with the restored canonical Phase D flow. For current frontend
> work, use [`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md)
> instead.

**Статус:** `REFERENCE`
**Прогресс:** не применяется
**Зависит от:** E01, E04
**Блокирует:** E03, стабильный production UX прихода

---

## Цель

Зафиксировать UX-принципы для нового workspace: создание, продолжение, редактирование и просмотр прихода должны жить в одном понятном рабочем интерфейсе. Пользователь не должен видеть один UX при создании черновика и другой UX при повторном входе в тот же приход.

## Контекст и обоснование

Старый frontend распался на два разных опыта:

- `IntakeCreate` — новый wizard с шагами `Основа / Товары / Условия / Проверка`;
- `IntakeDetail` — старый рабочий экран, куда пользователь попадает после выхода из прихода;
- часть новых сущностей показана только в wizard, часть операций живёт только в detail;
- источник финансирования, условия расчёта с поставщиком и физическая приёмка товара смешаны в одном выборе.

Это создаёт неправильное ощущение: незавершённый приход выглядит как "просмотр", хотя бизнес-процесс ещё продолжается.

## Главный принцип

Целевой `ProcurementWorkspace` должен быть не формой создания и не страницей просмотра, а **рабочим пространством прихода**.

Один и тот же экран открывается:

- при создании нового прихода;
- при продолжении `OPEN` прихода;
- при частично принятом `PARTIALLY_RECEIVED` приходе;
- при просмотре `RECEIVED/CLOSED` прихода.

Отличается только доступность действий. Видимость и расположение данных остаются стабильными.

## Current Canonical Flow Override

This document does not define the final Phase D order.

Current order:

```text
товары/расходы -> поставщик/условия -> источник денег -> оплата/обязательство -> приёмка -> история
```

See [`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md).

## Сущности, которые нельзя смешивать

### 1. Источник товара

Откуда приходит товар:

- поставщик;
- дистрибьютор как частный случай поставщика;
- разовая покупка без фиксированного поставщика;
- товар по консигнации;
- товар под партнёрский капитал.

`supplier_id` должен быть:

- опционален для простой покупки за свои деньги с полной оплатой;
- обязателен для отсрочки, рассрочки, частичной оплаты и консигнации;
- желателен для партнёрского прихода, но технически может быть пустым, если закупка разовая.

### 2. Источник финансирования

Кто финансирует закупку:

- `OWN_FUNDS` — бизнес финансирует сам;
- `PARTNERSHIP` — капитал партнёров/инвесторов;
- `SUPPLIER_CREDIT` — не отдельный `procurement_type`, а следствие условий поставщика: отсрочка, рассрочка, консигнация.

`MUSHARAKA` не должен быть отдельной кнопкой в UI. Это подтип/формула партнёрского договора, а не отдельный пользовательский сценарий прихода. Старый backend enum можно учитывать при mapping, но целевой интерфейс показывает "Партнёрское финансирование".

### 3. Условия расчёта с поставщиком

Как и когда бизнес рассчитывается за товар:

- `PREPAID` — оплачено сразу;
- `PARTIAL` — часть оплачена, остаток долг;
- `DEFERRED` — оплата позже одной суммой;
- `INSTALLMENT` — график платежей;
- `CONSIGNMENT` — реализация/консигнация.

Это не тип закупки. Это `ProcurementTerms`.

### 4. Состав прихода

Что входит в товарную стоимость:

- `ProcurementItem` — товары;
- `ProcurementExpense` — посадочные расходы;
- `ProcurementExpenseTarget` — к каким товарам применить расход;
- `cost_preview` — как расходы попадут в landed cost.

Расходы должны жить рядом с товарами, а не внутри "Условий". Это часть себестоимости прихода.

### 5. Денежное состояние прихода

Для партнёрского прихода есть отдельный денежный контур:

- кто внёс капитал;
- сколько лежит на балансе прихода;
- какие суммы потрачены;
- какие суммы распределены при приёмке.
