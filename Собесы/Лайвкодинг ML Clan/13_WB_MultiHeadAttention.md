# Wildberries CV — MultiHeadAttention

Источник: [Telegram #45529](https://t.me/c/2673339123/45529), текст сообщения.

Реализуйте `MultiHeadAttention` по выданному каркасу. Метод должен вернуть `(output, attention_weights)` и поддерживать вызов с маской и без неё.

```python
class MultiHeadAttention(nn.Module):
    def __init__(
        self,
        hid_dim: int,
        n_heads: int,
        dropout: float = 0.1,
    ) -> None:
        raise NotImplementedError

    def forward(
        self,
        x,
        mask=None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        raise NotImplementedError
```

## Твоя реализация

```python














```

> [!question] Вопрос / уточнение интервьюера
> Какие формы имеют Q, K и V до и после разделения на heads?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Какой размер имеет attention matrix до умножения на V?

**Твой ответ:**

<br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Когда и как применяется mask?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Где применяется dropout и как меняется поведение между train и eval?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Чем этот self-attention отличается от cross-attention?

**Твой ответ:**

<br><br><br><br>
