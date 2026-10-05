# Т-Банк — Decision Tree classifier на NumPy

Источники: [#86349](https://t.me/c/2673339123/86349), [#86353](https://t.me/c/2673339123/86353), [#86354](https://t.me/c/2673339123/86354), [#86355](https://t.me/c/2673339123/86355). Каркас восстановлен из текста и локального OCR.

Дан каркас классификационного дерева. В нём уже есть `NodeType(REGULAR, LEAF)`, `DecisionTreeNode`, `meta`, `depth`, `impurity`, поля `feature_id`, `threshold`, `predicted_class`, `class_proba`, `left_subtree`, `right_subtree`. Метод `predict` вызывает `predict_proba(x).argmax()`.

Нужно реализовать:

```python
def gini(y: np.ndarray) -> float:
    

def _weighted_gini_impurity(
    y_left: np.ndarray,
    y_right: np.ndarray,
) -> tuple[float, float, float]:
    

def _create_split(
    feature_values: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    

def _best_split(
    X: np.ndarray,
    y: np.ndarray,
) -> tuple[int, float, float, float]:
    

def fit(X: np.ndarray, y: np.ndarray) -> DecisionTreeNode:
    
```

> [!question] Вопрос / уточнение интервьюера
> Запишите критерий Gini и реализуйте его.

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как посчитать взвешенную impurity двух дочерних узлов?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Какие объекты попадут в левую и правую части при заданном threshold?

**Твой ответ:**

<br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как найти лучший признак и threshold и не создать пустой дочерний узел?

**Твой ответ:**

<br><br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Перечислите условия, при которых текущий узел становится листом.

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как заполнить `predicted_class` и `class_proba`?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как ускорить перебор возможных threshold?

**Твой ответ:**

<br><br><br><br>
