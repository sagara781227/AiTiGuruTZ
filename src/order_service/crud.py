from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, Tuple
from decimal import Decimal
import redis.asyncio as redis
import structlog

from src.order_service.models import Order, OrderItem, Product, Customer
from src.order_service.exceptions import (
    ProductNotAvailableError,
    OrderNotFoundError,
    ProductNotFoundError,
    OrderClosedError,
    ConcurrentModificationError,
    CustomerNotFoundError,
)
from src.order_service.config import settings

logger = structlog.get_logger()


class OrderCRUD:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis_client = None
        
        if settings.REDIS_URL:
            self.redis_client = redis.from_url(settings.REDIS_URL)
    
    async def acquire_lock(self, lock_key: str) -> bool:
        """Получение блокировки через Redis."""
        if not self.redis_client:
            return True
        
        try:
            acquired = await self.redis_client.set(
                lock_key, 
                "locked", 
                nx=True, 
                ex=settings.REDIS_LOCK_TIMEOUT
            )
            return bool(acquired)
        except Exception as e:
            logger.error("redis_lock_error", error=str(e), lock_key=lock_key)
            return True
    
    async def release_lock(self, lock_key: str) -> None:
        """Освобождение блокировки."""
        if self.redis_client:
            try:
                await self.redis_client.delete(lock_key)
            except Exception as e:
                logger.error("redis_unlock_error", error=str(e), lock_key=lock_key)
    
    async def create_order(self, customer_id: int) -> Order:
        """Создание нового заказа."""
        customer_stmt = select(Customer).where(Customer.id == customer_id)
        customer_result = await self.db.execute(customer_stmt)
        customer = customer_result.scalar_one_or_none()
        
        if not customer:
            raise CustomerNotFoundError(customer_id)
        
        from datetime import datetime
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{customer_id:06d}"
        
        order = Order(
            order_number=order_number,
            customer_id=customer_id,
            status="new",
            total_amount=0
        )
        
        self.db.add(order)
        await self.db.flush()
        await self.db.commit()
        
        await self.db.refresh(order)
        return order
    
    async def get_order_with_items(self, order_id: int) -> Optional[Order]:
        """Получение заказа со всеми позициями."""
        stmt = (
            select(Order)
            .options(
                selectinload(Order.order_items).joinedload(OrderItem.product),
                joinedload(Order.customer)
            )
            .where(Order.id == order_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_product_with_lock(self, product_id: int) -> Product:
        """Получение товара с пессимистичной блокировкой для обновления."""
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        product = result.scalar_one_or_none()
        
        if not product:
            raise ProductNotFoundError(product_id)
        
        return product
    
    async def check_and_reserve_product(
        self, 
        product_id: int, 
        quantity: Decimal
    ) -> Product:
        """Проверка доступности и резервирование товара."""
        product = await self.get_product_with_lock(product_id)
        
        if product.quantity < quantity:
            raise ProductNotAvailableError(
                product_id=product_id,
                available=float(product.quantity)
            )
        
        product.quantity -= quantity
        return product
    
    async def add_or_update_order_item(
        self,
        order_id: int,
        product_id: int,
        quantity: Decimal
    ) -> Tuple[Order, OrderItem, bool]:
        """
        Добавление или обновление товара в заказе.
        
        Возвращает: (заказ, позиция заказа, создана_ли_новая_позиция)
        """
        lock_key = f"order:{order_id}"
        if not await self.acquire_lock(lock_key):
            raise ConcurrentModificationError(order_id)
        
        try:
            order = await self.get_order_with_items(order_id)
            if not order:
                await self.db.rollback()
                raise OrderNotFoundError(order_id)
            
            if order.status not in ['new', 'processing']:
                await self.db.rollback()
                raise OrderClosedError(order_id, order.status)
            
            product = await self.check_and_reserve_product(product_id, quantity)
            
            existing_item = None
            for item in order.order_items:
                if item.product_id == product_id:
                    existing_item = item
                    break
            
            is_new_item = existing_item is None
            
            if existing_item:
                existing_item.quantity += quantity
                existing_item.subtotal = existing_item.quantity * existing_item.unit_price
                order_item = existing_item
            else:
                subtotal = quantity * product.price
                order_item = OrderItem(
                    order_id=order_id,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price=product.price,
                    subtotal=subtotal
                )
                self.db.add(order_item)
            
            await self.recalculate_order_total(order)
            
            await self.db.commit()
            
            await self.db.refresh(order)
            await self.db.refresh(order_item)
            
            return order, order_item, is_new_item
            
        except Exception as e:
            await self.db.rollback()
            logger.error("add_to_order_error", 
                        order_id=order_id, 
                        product_id=product_id, 
                        error=str(e))
            raise
        finally:
            await self.release_lock(lock_key)
    
    async def update_order_item_quantity(
        self,
        order_id: int,
        product_id: int,
        new_quantity: Decimal
    ) -> Tuple[Order, OrderItem]:
        """Обновление количества товара в заказе."""
        lock_key = f"order:{order_id}"
        if not await self.acquire_lock(lock_key):
            raise ConcurrentModificationError(order_id)
        
        try:
            order = await self.get_order_with_items(order_id)
            if not order:
                await self.db.rollback()
                raise OrderNotFoundError(order_id)
            
            if order.status not in ['new', 'processing']:
                await self.db.rollback()
                raise OrderClosedError(order_id, order.status)
            
            order_item = None
            for item in order.order_items:
                if item.product_id == product_id:
                    order_item = item
                    break
            
            if not order_item:
                await self.db.rollback()
                raise ProductNotFoundError(product_id)
            
            quantity_diff = new_quantity - order_item.quantity
            
            if quantity_diff > 0:
                product = await self.check_and_reserve_product(product_id, quantity_diff)
            elif quantity_diff < 0:
                product = await self.get_product_with_lock(product_id)
                product.quantity += abs(quantity_diff)
            
            order_item.quantity = new_quantity
            order_item.subtotal = new_quantity * order_item.unit_price
            
            await self.recalculate_order_total(order)
            
            await self.db.commit()
            
            await self.db.refresh(order)
            await self.db.refresh(order_item)
            
            return order, order_item
            
        except Exception as e:
            await self.db.rollback()
            logger.error("update_order_item_error",
                        order_id=order_id,
                        product_id=product_id,
                        error=str(e))
            raise
        finally:
            await self.release_lock(lock_key)
    
    async def remove_order_item(
        self,
        order_id: int,
        product_id: int
    ) -> Order:
        """Удаление товара из заказа."""
        lock_key = f"order:{order_id}"
        if not await self.acquire_lock(lock_key):
            raise ConcurrentModificationError(order_id)
        
        try:
            order = await self.get_order_with_items(order_id)
            if not order:
                await self.db.rollback()
                raise OrderNotFoundError(order_id)
            
            if order.status not in ['new', 'processing']:
                await self.db.rollback()
                raise OrderClosedError(order_id, order.status)
            
            order_item_to_delete = None
            for item in order.order_items:
                if item.product_id == product_id:
                    order_item_to_delete = item
                    break
            
            if not order_item_to_delete:
                await self.db.rollback()
                raise ProductNotFoundError(product_id)
            
            product = await self.get_product_with_lock(product_id)
            product.quantity += order_item_to_delete.quantity
            
            await self.db.delete(order_item_to_delete)
            
            await self.recalculate_order_total(order)
            
            await self.db.commit()
            await self.db.refresh(order)
            
            return order
            
        except Exception as e:
            await self.db.rollback()
            logger.error("remove_order_item_error",
                        order_id=order_id,
                        product_id=product_id,
                        error=str(e))
            raise
        finally:
            await self.release_lock(lock_key)
    
    async def recalculate_order_total(self, order: Order) -> None:
        """Пересчет общей суммы заказа."""
        stmt = select(func.sum(OrderItem.subtotal)).where(
            OrderItem.order_id == order.id
        )
        result = await self.db.execute(stmt)
        total = result.scalar() or 0
        order.total_amount = total