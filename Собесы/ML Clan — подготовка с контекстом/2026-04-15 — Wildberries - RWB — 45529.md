# Wildberries / RWB — 2026-04-15

- Interview: #45529
- Source: #45529

## Контекстный блок 1

Источник: #45529; OCR/текст источника.

> [!quote]- Исходный контекст и обсуждение
> Когда то в ноябре: 
> WB Computer vision Metric Learning  (несмотря что это был собес по CV, интервьюер занимался NLP) 1.5 часа
>
> 1. Что такое train() и eval()
> 2. Зачем нужен BatchNorm => подробно
> 3. Чем отличается работа BatchNorm на трейне и инференсе => про вычисление статистик и EMA
> 4. Какие нормализации ещё знаешь? => Layer, Instance, Group
> 5. Зачем нужен DropOut
> 6. Работа DropOut на трейне и на инференсе
> 7. Расскажи про метрики классификации
> 8. Микро и Макро усреднения в классификации
> 9. Как устроен оригинальный трансформер
> 10. В каких задач используется энкодер а где декодер
> 11. Какого размера будет матрица весов атеншн после softmax, но до умножения на value матрицу
> 12. Как устроен CLIP
> 12. Для обученной CLIP вычислили матрицу скалярных произведений между эмбеддингами картинок и эмбеддингами текстов. Как соотносятся средние значения на диагонали этой матрицы и за её пределами?
> 13. Что такое Metric Learning
> 14. Какие траблы в Metric Learning есть
> 15. Расскажи подробнее про hard negative mining 
> 16. В чем суть проблемы коллапса представлений при обучении в metric learning?
> 17. Про триплет лосс и когда нужно увеличивать margin
> 18. Проблемы triplet loss => реш: ArcFace
>
> Лайв кодинг — Реализуй класс MultiHeadAttn
>
> import torch
> import torch.nn as nn
> import torch.nn.functional as F
>
> class MultiHeadAttention(nn.Module):
>     def __init__(self, hid_dim: int, n_heads: int, dropout: float = 0.1) -> None:
>         """
>         Входные параметры:
>         - hid_dim: скрытая размерность
>         - n_heads: количество голов внимания
>         - dropout: вероятность занулить скор
>         """
>         raise NotImplementedError
>
>     def forward(
>         self, x: torch.Tensor, mask: torch.Tensor | None = None
>     ) -> tuple[torch.Tensor, torch.Tensor]:
>         """
>         Напишите свой forward для MultiHeadAttention.
>
>         Функция должна вернуть tuple (выход слоя, attention веса).
>         """
>  
>         raise NotImplementedError
>
>
> input_tensor = torch.randn((...))  
> mask = ... 
> m = MultiHeadAttention(...) 
>
> out, attn_scores = m(x=input_tensor, mask=None)
> print(out.shape, attn_scores)
>
> out, attn_scores = m(x=input_tensor, mask=mask)
> print(out.shape, attn_scores)

### Связанные вопросы

- Зачем нужен Batch Normalization? — #45529
- Как BatchNorm вычисляет статистики mini-batch, обновляет moving averages и использует их при inference? — #45529
- Напишите `forward` для Multi-Head Attention. — #45529
- Опишите архитектуру оригинального Transformer: encoder, decoder, causal self-attention и cross-attention между ними. — #45529
- Чем работа BatchNorm на train отличается от inference? — #45529
- Что такое dropout и зачем он нужен? — #45529
