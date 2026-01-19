from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from decimal import Decimal


class OrderCreate(BaseModel):
    """Схема для создания нового заказа."""
    customer_id: int = Field(..., gt=0, description="ID клиента")


class OrderItemAddRequest(BaseModel):
    """Схема для добавления товара в заказ."""
    order_id: int = Field(..., gt=0, description="ID заказа")
    product_id: int = Field(..., gt=0, description="ID товара")
    quantity: Decimal = Field(..., gt=0, description="Количество товара", max_digits=10, decimal_places=3)
    
    @validator('quantity')
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError('Количество должно быть больше 0')
        return v


class OrderItemRemoveRequest(BaseModel):
    """Схема для удаления товара из заказа."""
    order_id: int = Field(..., gt=0, description="ID заказа")
    product_id: int = Field(..., gt=0, description="ID товара")


class OrderItemResponse(BaseModel):
    """Схема ответа для позиции заказа."""
    id: int
    order_id: int
    product_id: int
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal
    
    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Схема ответа для заказа."""
    id: int
    order_number: str
    customer_id: int
    customer_name: Optional[str] = None
    status: str
    total_amount: Decimal
    order_date: datetime
    order_items: list[OrderItemResponse] = []
    
    class Config:
        from_attributes = True


class SuccessResponse(BaseModel):
    """Схема успешного ответа."""
    success: bool = True
    message: str
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Схема ошибки."""
    error: str
    message: str
    details: Optional[dict] = None