from fastapi import HTTPException, status


class OrderServiceError(HTTPException):
    """Базовое исключение сервиса заказов."""
    pass


class ProductNotAvailableError(OrderServiceError):
    """Товар недоступен."""
    def __init__(self, product_id: int, available: float):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "product_not_available",
                "message": f"Товар {product_id} недоступен в количестве {available}",
                "product_id": product_id,
                "available_quantity": available
            }
        )


class OrderNotFoundError(OrderServiceError):
    """Заказ не найден."""
    def __init__(self, order_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "order_not_found",
                "message": f"Заказ {order_id} не найден",
                "order_id": order_id
            }
        )


class ProductNotFoundError(OrderServiceError):
    """Товар не найден."""
    def __init__(self, product_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "product_not_found",
                "message": f"Товар {product_id} не найден",
                "product_id": product_id
            }
        )


class OrderClosedError(OrderServiceError):
    """Заказ уже закрыт."""
    def __init__(self, order_id: int, status: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "order_closed",
                "message": f"Заказ {order_id} имеет статус '{status}' и не может быть изменен",
                "order_id": order_id,
                "current_status": status
            }
        )


class ConcurrentModificationError(OrderServiceError):
    """Конкурентное изменение данных."""
    def __init__(self, order_id: int):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "concurrent_modification",
                "message": f"Заказ {order_id} был изменен другим запросом",
                "order_id": order_id
            }
        )

class CustomerNotFoundError(OrderServiceError):
    """Клиент не найден."""
    def __init__(self, customer_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "customer_not_found",
                "message": f"Клиент {customer_id} не найден",
                "customer_id": customer_id
            }
        )