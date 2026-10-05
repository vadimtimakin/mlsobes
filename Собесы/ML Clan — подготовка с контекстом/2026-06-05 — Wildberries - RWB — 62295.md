# Wildberries / RWB — 2026-06-05

- Interview: #62295
- Source: #62295, #62296
- Этап: Техническая секция

## Контекстный блок 1

Источник: #62296; OCR/текст источника.

> [!quote]- Исходный контекст и обсуждение
> WITH num AS (
> SELECT user_id, dt, dt - ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY dt) AS grp
> FROM daily_active
> streak AS
> SELECT user_id, grp,
> COUNT(*) AS len
> FROM num
> GRoup BY user_id, grp
> SELECT distinct user_id
> FROM streak
> WHERE len >= 3
> def f(x=[]):
> x.append(1)
> return x
> f(), f()
> Mawa
> a = [1,2,3];b = a.copy(); b.append(4)

### Связанные вопросы

- В таблице `daily_active(dt, user_id)` найдите пользователей с серией не менее трёх последовательных дней через ключ `date − ROW_NUMBER()`. Как сначала удалить дубли дня и корректно работать с типом `DATE`? — #62295, #62296
- Что вернут два последовательных вызова функции `f(x=[])`, которая добавляет элемент в `x`, и почему default-list создаётся один раз при определении функции? — #62296
- Что произойдёт с `a = [1,2,3]` после `b = a.copy(); b.append(4)`, и чем результат изменится при модификации вложенного mutable-элемента? — #62296
