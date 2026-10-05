# Авито — TF-IDF и Python

Источники: [#88920](https://t.me/c/2673339123/88920), [#88921](https://t.me/c/2673339123/88921), [#88922](https://t.me/c/2673339123/88922), [#88923](https://t.me/c/2673339123/88923). Задания восстановлены локальным OCR.

## 1. TF-IDF

Реализуйте класс `TF_IDF` с обучением на корпусе и преобразованием документов.

```python
class TF_IDF:
    def __init__(self):
        

    def fit(self, documents: list[str]):
        

    def transform(self, documents: list[str]):
        

    def fit_transform(self, documents: list[str]):
        
```

> [!question] Вопрос / уточнение интервьюера
> Как определяются TF и IDF?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Где хранить vocabulary и рассчитанные IDF?

**Твой ответ:**

<br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Как обработать токены, которых не было при fit?

**Твой ответ:**

<br><br><br>

## 2. LEGB

Назовите вывод и объясните поиск каждого имени.

```python
x = 5

def f():
    x = 10

    def g():
        x = 15
        print(x)

    g()
    print(x)

f()
print(x)
```

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Чем `nonlocal` отличается от `global`?

**Твой ответ:**

<br><br><br>

## 3. Decorator

Реализуйте `@start_end`, чтобы до и после вызова функции печатались `f start` и `f end`. Функция внутри печатает `123`.

```python
@start_end
def f():
    print(123)
```

```python
def start_end(func):
    
```

> [!question] Вопрос / уточнение интервьюера
> Как сохранить аргументы, возвращаемое значение и metadata исходной функции?

**Твой ответ:**

<br><br><br><br>

> [!question] Вопрос / уточнение интервьюера
> Будет ли `f end` напечатано, если функция выбросит исключение?

**Твой ответ:**

<br><br><br>

## 4. Exceptions

В `try` возникает `ValueError`; первый `except` ловит `ZeroDivisionError`, второй — `Exception`, после них есть `else` и `finally`. Назовите, какие блоки выполнятся и в каком порядке.

Точный фрагмент: [#88923](https://t.me/c/2673339123/88923).

**Твой ответ:**

<br><br><br><br>
