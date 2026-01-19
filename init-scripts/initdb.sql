-- 1. Создание таблиц

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    parent_id INTEGER NULL,
    path VARCHAR(255) NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK (level >= 1),
    
    CONSTRAINT fk_categories_parent 
        FOREIGN KEY (parent_id) 
        REFERENCES categories(id) 
        ON DELETE CASCADE,
    
    CONSTRAINT chk_not_self_reference 
        CHECK (parent_id IS NULL OR parent_id != id)
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    category_id INTEGER NOT NULL,
    
    CONSTRAINT fk_products_category 
        FOREIGN KEY (category_id) 
        REFERENCES categories(id) 
        ON DELETE RESTRICT
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    address TEXT
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    order_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'new' 
        CHECK (status IN ('new', 'processing', 'shipped', 'delivered', 'cancelled')),
    total_amount DECIMAL(12, 2) DEFAULT 0 CHECK (total_amount >= 0),
    
    CONSTRAINT fk_orders_customer 
        FOREIGN KEY (customer_id) 
        REFERENCES customers(id) 
        ON DELETE RESTRICT
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity DECIMAL(10, 3) NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
    subtotal DECIMAL(12, 2) NOT NULL CHECK (subtotal >= 0),
    
    CONSTRAINT fk_order_items_order 
        FOREIGN KEY (order_id) 
        REFERENCES orders(id) 
        ON DELETE CASCADE,
    
    CONSTRAINT fk_order_items_product 
        FOREIGN KEY (product_id) 
        REFERENCES products(id) 
        ON DELETE RESTRICT,
    
    CONSTRAINT uniq_order_product UNIQUE (order_id, product_id)
);

-- 2. Функции и триггеры для поддержки path в категориях

CREATE OR REPLACE FUNCTION update_category_path()
RETURNS TRIGGER AS $$
DECLARE
    parent_path VARCHAR;
    parent_level INTEGER;
BEGIN
    IF NEW.parent_id IS NULL THEN
        NEW.path = NEW.id || '/';
        NEW.level = 1;
    ELSE
        SELECT path, level INTO parent_path, parent_level
        FROM categories 
        WHERE id = NEW.parent_id;
        
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Parent category with id % not found', NEW.parent_id;
        END IF;
        
        NEW.path = parent_path || NEW.id || '/';
        NEW.level = parent_level + 1;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_category_insert_path
    BEFORE INSERT ON categories
    FOR EACH ROW
    EXECUTE FUNCTION update_category_path();

CREATE TRIGGER trg_category_update_path
    BEFORE UPDATE ON categories
    FOR EACH ROW
    WHEN (OLD.parent_id IS DISTINCT FROM NEW.parent_id)
    EXECUTE FUNCTION update_category_path();

CREATE OR REPLACE FUNCTION update_children_paths()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.path IS DISTINCT FROM NEW.path THEN
        UPDATE categories 
        SET path = REPLACE(path, OLD.path, NEW.path),
            level = length(regexp_replace(REPLACE(path, OLD.path, NEW.path), '[^/]', '', 'g'))
        WHERE path LIKE OLD.path || '%' 
          AND id != NEW.id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_category_update_children_paths
    AFTER UPDATE OF path ON categories
    FOR EACH ROW
    WHEN (OLD.path IS DISTINCT FROM NEW.path)
    EXECUTE FUNCTION update_children_paths();

-- 3. Вспомогательные функции для работы с деревом

-- Функция для получения всех потомков категории (включая саму категорию)
CREATE OR REPLACE FUNCTION get_category_descendants(root_id INTEGER)
RETURNS TABLE(
    id INTEGER,
    name VARCHAR,
    parent_id INTEGER,
    path VARCHAR,
    level INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.name, c.parent_id, c.path, c.level
    FROM categories c
    WHERE c.path LIKE (
        SELECT path FROM categories WHERE id = root_id
    ) || '%'
    ORDER BY c.path;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения цепочки предков категории (от корня до текущей)
CREATE OR REPLACE FUNCTION get_category_ancestors(category_id INTEGER)
RETURNS TABLE(
    id INTEGER,
    name VARCHAR,
    level INTEGER,
    is_current BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE ancestors AS (
        SELECT id, name, parent_id, level, true as is_current
        FROM categories
        WHERE id = category_id
        
        UNION ALL
        
        SELECT c.id, c.name, c.parent_id, c.level, false
        FROM categories c
        INNER JOIN ancestors a ON c.id = a.parent_id
    )
    SELECT a.id, a.name, a.level, a.is_current
    FROM ancestors a
    ORDER BY a.level;
END;
$$ LANGUAGE plpgsql;

-- Функция для проверки, не создается ли циклическая ссылка
CREATE OR REPLACE FUNCTION check_category_cycle()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        WITH RECURSIVE parents AS (
            SELECT id, parent_id
            FROM categories
            WHERE id = NEW.parent_id
            
            UNION ALL
            
            SELECT c.id, c.parent_id
            FROM categories c
            INNER JOIN parents p ON c.id = p.parent_id
        )
        SELECT 1 FROM parents WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'Cyclic reference detected: category % cannot be a descendant of itself', NEW.id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для предотвращения циклических ссылок
CREATE TRIGGER trg_check_category_cycle
    BEFORE INSERT OR UPDATE ON categories
    FOR EACH ROW
    EXECUTE FUNCTION check_category_cycle();

-- 4. Функция для пересчета общей суммы заказа

CREATE OR REPLACE FUNCTION update_order_total()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE orders 
        SET total_amount = COALESCE((
            SELECT SUM(subtotal) 
            FROM order_items 
            WHERE order_id = OLD.order_id
        ), 0)
        WHERE id = OLD.order_id;
    ELSE
        UPDATE orders 
        SET total_amount = COALESCE((
            SELECT SUM(subtotal) 
            FROM order_items 
            WHERE order_id = NEW.order_id
        ), 0)
        WHERE id = NEW.order_id;
    END IF;
    
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_order_items_update_total
    AFTER INSERT OR UPDATE OR DELETE ON order_items
    FOR EACH ROW
    EXECUTE FUNCTION update_order_total();

-- 5. Индексы для оптимизации производительности

-- Индексы для categories
CREATE INDEX idx_categories_parent_id ON categories(parent_id);
CREATE INDEX idx_categories_path ON categories(path);
CREATE INDEX idx_categories_level ON categories(level);
CREATE INDEX idx_categories_path_pattern ON categories(path text_pattern_ops);

-- Индексы для products
CREATE INDEX idx_products_category_id ON products(category_id);
CREATE INDEX idx_products_name ON products(name);

-- Индексы для customers
CREATE INDEX idx_customers_name ON customers(name);

-- Индексы для orders
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_order_date ON orders(order_date);
CREATE INDEX idx_orders_order_number ON orders(order_number);

-- Индексы для order_items
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);

-- 6. Генератор номеров заказов

CREATE SEQUENCE order_number_seq START WITH 1000;

CREATE OR REPLACE FUNCTION generate_order_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.order_number IS NULL THEN
        NEW.order_number = 'ORD-' || to_char(CURRENT_DATE, 'YYYYMMDD-') || 
                          lpad(nextval('order_number_seq')::text, 6, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_order_number
    BEFORE INSERT ON orders
    FOR EACH ROW
    EXECUTE FUNCTION generate_order_number();

-- 7. Запросы из пункта задания 2 в виде VIEW

-- 7.1. Получение информации о сумме товаров заказанных под каждого клиента
-- Вариант 1: Используем уже рассчитанное поле total_amount из orders
CREATE VIEW customer_order_total_v1 AS
SELECT c.name AS "Наименование клиента"
      ,COALESCE(SUM(o.total_amount), 0) AS "Сумма заказов"
  FROM customers c
       LEFT JOIN orders o ON c.id = o.customer_id
 WHERE o.status != 'cancelled'
 GROUP BY c.id, c.name
 ORDER BY "Сумма заказов" DESC;
-- Вариант 2: Пересчитываем сумму через order_items (более точный, но медленнее)
CREATE VIEW customer_order_total_v2 AS
SELECT c.name AS "Наименование клиента"
      ,COALESCE(SUM(oi.subtotal), 0) AS "Сумма заказов"
  FROM customers c
       LEFT JOIN orders o ON c.id = o.customer_id 
                         AND o.status != 'cancelled'
       LEFT JOIN order_items oi ON o.id = oi.order_id
 GROUP BY c.id, c.name
 ORDER BY "Сумма заказов" DESC;

-- 7.2. Количество дочерних элементов первого уровня вложенности для категорий
-- Вариант 1: Стандартный подход с JOIN
CREATE VIEW category_child_count_v1 AS
SELECT parent.id AS "ID категории"
      ,parent.name AS "Название категории"
      ,COUNT(child.id) AS "Количество дочерних категорий 1-го уровня"
  FROM categories parent
       LEFT JOIN categories child ON parent.id = child.parent_id
 GROUP BY parent.id, parent.name
 ORDER BY parent.id;
-- Вариант 2: Более быстрый вариант с использованием path
CREATE VIEW category_child_count_v2 AS
SELECT id AS "ID категории"
      ,name AS "Название категории"
      ,(
           SELECT COUNT(*)
             FROM categories child
            WHERE child.parent_id = parent.id
       ) AS "Количество дочерних категорий 1-го уровня"
  FROM categories parent
 ORDER BY id;

-- 7.3 Топ-5 самых покупаемых товаров за последний месяц
-- Вариант 1: Идем обычным путем
CREATE OR REPLACE VIEW top_5_products_last_month AS
WITH monthly_sales AS (
    SELECT p.id AS product_id
          ,p.name AS product_name
          ,(
               SELECT c2.name 
               FROM categories c2 
               WHERE c2.id = split_part(c.path, '/', 1)::integer
           ) AS root_category_name
          ,SUM(oi.quantity) AS total_quantity_sold
          ,COUNT(DISTINCT o.id) AS order_count
      FROM orders o
           JOIN order_items oi ON o.id = oi.order_id
           JOIN products p ON oi.product_id = p.id
           JOIN categories c ON p.category_id = c.id
     WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
       AND o.order_date < DATE_TRUNC('month', CURRENT_DATE)
       AND o.status NOT IN ('cancelled')
     GROUP BY p.id, p.name, c.path
)
SELECT product_name AS "Наименование товара"
      ,root_category_name AS "Категория 1-го уровня"
      ,total_quantity_sold AS "Общее количество проданных штук"
      ,RANK() OVER (ORDER BY total_quantity_sold DESC) AS sales_rank
  FROM monthly_sales
 ORDER BY total_quantity_sold DESC
 LIMIT 5;
-- Вариант 2: С использованием функции для получения корневой категории
-- Создаем вспомогательную функцию для получения корневой категории
CREATE OR REPLACE FUNCTION get_root_category_id(category_path VARCHAR)
RETURNS INTEGER AS $$
BEGIN
    RETURN split_part(category_path, '/', 1)::integer;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Оптимизированный запрос с использованием функции
CREATE OR REPLACE VIEW top_5_products_last_month_optimized AS
SELECT p.name AS "Наименование товара"
      ,root_cat.name AS "Категория 1-го уровня"
      ,SUM(oi.quantity) AS "Общее количество проданных штук"
  FROM orders o
       JOIN order_items oi ON o.id = oi.order_id
       JOIN products p ON oi.product_id = p.id
       JOIN categories cat ON p.category_id = cat.id
       JOIN categories root_cat ON root_cat.id = get_root_category_id(cat.path)
 WHERE o.order_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
   AND o.order_date < DATE_TRUNC('month', CURRENT_DATE)
   AND o.status NOT IN ('cancelled')
 GROUP BY p.id, p.name, root_cat.name
 ORDER BY SUM(oi.quantity) DESC
 LIMIT 5;

 -- 8. Тестовые данные
INSERT INTO categories (name, parent_id) VALUES
('Электроника', NULL),
('Бытовая техника', NULL),
('Одежда', NULL);

INSERT INTO categories (name, parent_id) VALUES
('Смартфоны', 1),
('Ноутбуки', 1),
('Apple', 4),
('Samsung', 4),
('Крупная техника', 2),
('Мелкая техника', 2),
('Холодильники', 8),
('Стиральные машины', 8);

INSERT INTO products (name, quantity, price, category_id) VALUES
('iPhone 15 Pro', 50, 99999.99, 6),
('MacBook Air M2', 25, 89999.99, 5),
('Galaxy S24', 40, 79999.99, 7),
('Холодильник Bosch', 15, 59999.99, 10),
('Стиральная машина LG', 20, 34999.99, 11);

INSERT INTO customers (name, phone, address) VALUES
('Иванов Иван Иванович', '+7 (999) 123-45-67', 'г. Москва, ул. Ленина, д. 10, кв. 25'),
('Петрова Мария Сергеевна', '+7 (916) 987-65-43', 'г. Санкт-Петербург, Невский пр., д. 50'),
('Сидоров Алексей Петрович', '+7 (903) 555-55-55', 'г. Екатеринбург, ул. Мира, д. 15');