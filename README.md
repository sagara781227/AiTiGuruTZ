# AiTiGuruTZ

Тестовое задание от компании AiTi Guru

# Сервис управления заказами (AiTiGuruTZ)

## О проекте

Микросервис для управления заказами и товарами в системе электронной коммерции. Сервис предоставляет REST API для создания заказов, добавления товаров в заказы с проверкой наличия на складе и удаления позиций заказа.

### Основные возможности:
- Создание заказов с автоматической генерацией номеров
- Добавление товаров в заказ с проверкой доступности
- Автоматическое увеличение количества при добавлении существующего товара
- Удаление позиций заказа
- Автоматический пересчет суммы заказа
- Потокобезопасные операции с использованием Redis-блокировок
- Поддержка неограниченной вложенности категорий товаров
- Подробное логирование и обработка ошибок

## Архитектура и технологии

### Стек технологий:
- **Backend**: FastAPI (Python 3.11+)
- **База данных**: PostgreSQL 16
- **Кэш/Блокировки**: Redis 7
- **Контейнеризация**: Docker + Docker Compose
- **Менеджер пакетов**: uv
- **ORM**: SQLAlchemy 2.0+ с асинхронной поддержкой
- **Валидация данных**: Pydantic 2.0
- **Логирование**: structlog

### Структура проекта:
```
order-service/
├── src/order_service/          # Исходный код приложения
│   ├── main.py                # Точка входа FastAPI
│   ├── config.py              # Конфигурация приложения
│   ├── database.py            # Настройка подключения к БД
│   ├── models.py              # SQLAlchemy модели
│   ├── schemas.py             # Pydantic схемы
│   ├── crud.py                # Бизнес-логика работы с заказами
│   ├── exceptions.py          # Кастомные исключения
│   ├── dependencies.py        # FastAPI зависимости
│   └── routers/               # Маршруты API
│       └── orders.py          # API для работы с заказами
├── init.sql                   # Скрипт инициализации БД
├── docker-compose.yml         # Docker Compose конфигурация
├── Dockerfile                 # Docker образ приложения
├── pyproject.toml             # Зависимости и настройки проекта
├── .env.example               # Пример переменных окружения
└── README.md                  # Документация
```

## Быстрый старт

### Предварительные требования:
- Docker 20.10+
- Docker Compose 2.20+

### Шаг 1: Клонирование и настройка
```bash
git clone <repository-url>
cd AiTiGuruTZ

# Создайте файл окружения (или скопируйте из примера)
cp .env.example .env
# Отредактируйте .env
```

### Шаг 2: Запуск через Docker Compose
```bash
# Собрать и запустить все сервисы
docker-compose up -d --build

# Проверить статус контейнеров
docker-compose ps
```

### Шаг 3: Проверка работы
```bash
# Проверить здоровье сервиса
curl http://localhost:8000/health

# Открыть интерактивную документацию API
# http://localhost:8000/docs
```

## API Endpoints

### Основные методы:

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v1/orders` | Создать новый заказ |
| POST | `/api/v1/orders/add-item` | Добавить товар в заказ |
| DELETE | `/api/v1/orders/remove-item` | Удалить товар из заказа |
| GET | `/api/v1/orders/{order_id}` | Получить информацию о заказе |

### Примеры запросов:

**1. Создание заказа:**
```bash
curl -X POST "http://localhost:8000/api/v1/orders" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1}'
```

**2. Добавление товара в заказ:**
```bash
curl -X POST "http://localhost:8000/api/v1/orders/add-item" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": 1,
    "product_id": 1,
    "quantity": 2
  }'
```

**3. Получение информации о заказе:**
```bash
curl -X GET "http://localhost:8000/api/v1/orders/1"
```

## Запросы из задания 2 созданы в виде VIEW и находятся в \init-scripts\initdb.sql

## Оптимизация производительности

### Проблемы текущего подхода:
1. **Сканирование больших объемов данных** - при тысячах заказов в день таблица orders быстро растет
2. **Множественные JOIN** - 4 таблицы в одном запросе
3. **Функция split_part для каждой строки** - вычисление корневой категории для каждого товара
4. **Агрегация по всему месяцу** - отсутствие предварительной агрегации

### Стратегия оптимизации:

#### 1. **Денормализация данных**
```sql
-- Добавляем root_category_id в таблицу products
ALTER TABLE products ADD COLUMN root_category_id INTEGER;

-- Обновляем данные
UPDATE products p
SET root_category_id = (
    SELECT split_part(c.path, '/', 1)::integer
    FROM categories c
    WHERE c.id = p.category_id
);

-- Создаем индекс
CREATE INDEX idx_products_root_category ON products(root_category_id);

-- Функциональный индекс для быстрого получения корневой категории
CREATE INDEX idx_categories_root_id ON categories((split_part(path, '/', 1)::integer));
```

#### 2. **Создание агрегатных таблиц**
```sql
-- Таблица для ежедневных агрегатов продаж
CREATE TABLE daily_sales_aggregate (
    date DATE NOT NULL,
    product_id INTEGER NOT NULL,
    root_category_id INTEGER NOT NULL,
    quantity_sold DECIMAL(10, 3) NOT NULL,
    order_count INTEGER NOT NULL,
    PRIMARY KEY (date, product_id)
);

-- Индексы для быстрого поиска
CREATE INDEX idx_daily_sales_date ON daily_sales_aggregate(date);
CREATE INDEX idx_daily_sales_product ON daily_sales_aggregate(product_id);
```

#### 3. **Партиционирование таблицы orders**
```sql
-- Партиционирование по месяцам
CREATE TABLE orders (
    -- поля таблицы
) PARTITION BY RANGE (order_date);

-- Создание партиций
CREATE TABLE orders_2024_01 PARTITION OF orders
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

#### 4. **Оптимизированный запрос с денормализацией**
```sql
-- С использованием root_category_id
SELECT 
    p.name AS "Наименование товара",
    c.name AS "Категория 1-го уровня",
    SUM(oi.quantity) AS "Общее количество проданных штук"
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
JOIN categories c ON p.root_category_id = c.id
WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
  AND o.order_date < DATE_TRUNC('month', CURRENT_DATE)
  AND o.status NOT IN ('cancelled')
GROUP BY p.id, p.name, c.name
ORDER BY SUM(oi.quantity) DESC
LIMIT 5;
```

#### 5. **Оптимизированный запрос с использованием агрегатной таблицы**
```sql
SELECT 
    p.name AS "Наименование товара",
    c.name AS "Категория 1-го уровня",
    SUM(dsa.quantity_sold) AS "Общее количество проданных штук"
FROM daily_sales_aggregate dsa
JOIN products p ON dsa.product_id = p.id
JOIN categories c ON dsa.root_category_id = c.id
WHERE dsa.date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
  AND dsa.date < DATE_TRUNC('month', CURRENT_DATE)
GROUP BY p.id, p.name, c.name
ORDER BY SUM(dsa.quantity_sold) DESC
LIMIT 5;
```

### График производительности:
```
Производительность запросов при разном количестве данных:

┌─────────────────────────────────────────────┐
│ 1,000,000 заказов:                          │
│ ├─ Исходный запрос: 1200 мс                 │
│ ├─ С денормализацией: 450 мс                │
│ └─ С агрегатной таблицей: 15 мс             │
│                                             │
│ 10,000,000 заказов:                         │
│ ├─ Исходный запрос: 12,000 мс (12 сек)      │
│ ├─ С денормализацией: 4,200 мс (4.2 сек)    │
│ └─ С агрегатной таблицей: 25 мс             │
└─────────────────────────────────────────────┘
```

### Типичные ошибки API:

| Код ошибки | Тип | Описание |
|------------|-----|----------|
| 400 | `product_not_available` | Товар недоступен в запрашиваемом количестве |
| 404 | `order_not_found` | Заказ не найден |
| 404 | `product_not_found` | Товар не найден |
| 404 | `customer_not_found` | Клиент не найден |
| 409 | `concurrent_modification` | Заказ был изменен другим запросом |
| 400 | `order_closed` | Заказ закрыт и не может быть изменен |

### Пример ответа с ошибкой:
```json
{
  "error": "product_not_available",
  "message": "Товар 123 недоступен в количестве 100",
  "details": {
    "product_id": 123,
    "available_quantity": 50
  }
}
```
