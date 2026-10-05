# Wildberries RecSys — sampled softmax

Источник: [Telegram #52732](https://t.me/c/2673339123/52732), приложенная расшифровка.

Есть positive scores, in-batch negative scores и random negative scores. Масштаб: sequence length около `1024`, batch около `512`, примерно `8000` negatives.

## Часть 1. Убрать `torch.cat`

Получите результат, эквивалентный выражению ниже, не создавая конкатенированный тензор:

```python
torch.logsumexp(
    torch.cat([pos_scores, in_batch_scores, random_scores], dim=1),
    dim=1,
)
```

```python
def block_logsumexp(
    pos_scores: torch.Tensor,
    in_batch_scores: torch.Tensor,
    random_scores: torch.Tensor,
) -> torch.Tensor:
    
```

> [!question] Вопрос / уточнение интервьюера
> Почему отдельные `logsumexp` блоков нельзя просто сложить?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как избежать overflow на scores `90`, `99`, `100`?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как получить общий построчный максимум без конкатенации? Где нужен `keepdim`?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как проверить численную эквивалентность исходной и новой реализаций и сравнить peak memory?

**Твой ответ:**

<br><br><br><br>

## Часть 2. Не материализовывать score matrices

Даже без `torch.cat` матрицы scores уже занимают память. Предложите streaming/chunked forward и custom backward без хранения полных score matrices.

> [!question] Вопрос / уточнение интервьюера
> Какие sufficient statistics нужно сохранить из forward для backward?

**Твой ответ:**

<br><br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Запишите формы градиентов по скаляру, вектору и temperature.

**Твой ответ:**

<br><br><br><br><br>
