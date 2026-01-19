from sqlalchemy import (
    Column, Integer, String, Numeric, 
    DateTime, ForeignKey, Text, CheckConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from src.order_service.database import Base


class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    path = Column(String(255), nullable=True)
    level = Column(Integer, nullable=False, default=1)
    
    __table_args__ = (
        CheckConstraint("level >= 1", name="check_level_positive"),
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="chk_not_self_reference"),
    )
    
    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False, default=0)
    price = Column(Numeric(12, 2), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="check_quantity_non_negative"),
        CheckConstraint("price >= 0", name="check_price_non_negative"),
    )
    
    category = relationship("Category", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    order_date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(
        String(50), 
        nullable=False, 
        default="new",
        server_default="new"
    )
    total_amount = Column(Numeric(12, 2), default=0, nullable=False)
    
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="check_total_amount_non_negative"),
        CheckConstraint(
            "status IN ('new', 'processing', 'shipped', 'delivered', 'cancelled')",
            name="check_valid_status"
        ),
    )
    
    customer = relationship("Customer")
    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Numeric(10, 3), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)  # Убираем generated и делаем обычное поле
    
    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="check_unit_price_non_negative"),
        CheckConstraint("subtotal >= 0", name="check_subtotal_non_negative"),
        Index('idx_order_product_unique', 'order_id', 'product_id', unique=True),
    )
    
    order = relationship("Order", back_populates="order_items")
    product = relationship("Product", back_populates="order_items")