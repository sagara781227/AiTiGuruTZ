from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.order_service.schemas import (
    OrderCreate,
    OrderItemAddRequest,
    OrderItemRemoveRequest,
    OrderResponse,
    SuccessResponse,
    ErrorResponse,
)
from src.order_service.crud import OrderCRUD
from src.order_service.dependencies import get_db
from src.order_service.exceptions import OrderServiceError, OrderNotFoundError


router = APIRouter(
    prefix="/api/v1",
    tags=["orders"],
    responses={
        400: {"model": ErrorResponse, "description": "Ошибка валидации"},
        404: {"model": ErrorResponse, "description": "Ресурс не найден"},
        500: {"model": ErrorResponse, "description": "Внутренняя ошибка сервера"},
    }
)

logger = structlog.get_logger()


@router.post(
    "/orders",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый заказ",
    description="Создает новый заказ для указанного клиента"
)
async def create_order(
    order_data: OrderCreate,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Создание нового заказа.
    
    - **customer_id**: ID клиента (обязательно)
    """
    try:
        logger.info("create_order.request", customer_id=order_data.customer_id)
        
        crud = OrderCRUD(db)
        order = await crud.create_order(customer_id=order_data.customer_id)
        
        logger.info("create_order.success", 
                   order_id=order.id, 
                   order_number=order.order_number)
        
        return SuccessResponse(
            message="Заказ успешно создан",
            data={
                "order_id": order.id,
                "order_number": order.order_number,
                "customer_id": order.customer_id,
                "status": order.status,
                "total_amount": float(order.total_amount),
                "order_date": order.order_date.isoformat()
            }
        )
        
    except OrderServiceError as e:
        raise e
    except Exception as e:
        logger.error("create_order.error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "Произошла внутренняя ошибка сервера"
            }
        )


@router.post(
    "/orders/add-item",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Добавить товар в заказ",
    description="Добавляет товар в существующий заказ. Если товар уже есть, увеличивает его количество."
)
async def add_item_to_order(
    request: OrderItemAddRequest,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Добавление товара в заказ.
    
    - **order_id**: ID заказа (обязательно)
    - **product_id**: ID товара (обязательно)
    - **quantity**: Количество товара (обязательно, больше 0)
    """
    try:
        logger.info("add_item_to_order.request",
                   order_id=request.order_id,
                   product_id=request.product_id,
                   quantity=float(request.quantity))
        
        crud = OrderCRUD(db)
        order, order_item, is_new = await crud.add_or_update_order_item(
            order_id=request.order_id,
            product_id=request.product_id,
            quantity=request.quantity
        )
        
        action = "добавлен" if is_new else "обновлен"
        
        logger.info("add_item_to_order.success",
                   order_id=order.id,
                   product_id=order_item.product_id,
                   action=action,
                   total_quantity=float(order_item.quantity))
        
        return SuccessResponse(
            message=f"Товар успешно {action} в заказ",
            data={
                "order_id": order.id,
                "order_number": order.order_number,
                "order_status": order.status,
                "order_total": float(order.total_amount),
                "item_id": order_item.id,
                "product_id": order_item.product_id,
                "quantity": float(order_item.quantity),
                "unit_price": float(order_item.unit_price),
                "subtotal": float(order_item.quantity * order_item.unit_price),
                "is_new_item": is_new
            }
        )
        
    except OrderServiceError as e:
        logger.warning("add_item_to_order.service_error",
                      order_id=request.order_id,
                      error=e.detail["error"])
        raise e
    except Exception as e:
        logger.error("add_item_to_order.unexpected_error",
                    order_id=request.order_id,
                    error=str(e),
                    exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "Произошла внутренняя ошибка сервера"
            }
        )


@router.delete(
    "/orders/remove-item",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Удалить товар из заказа",
    description="Удаляет товар из существующего заказа"
)
async def remove_item_from_order(
    request: OrderItemRemoveRequest,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Удаление товара из заказа.
    
    - **order_id**: ID заказа (обязательно)
    - **product_id**: ID товара (обязательно)
    """
    try:
        logger.info("remove_item_from_order.request",
                   order_id=request.order_id,
                   product_id=request.product_id)
        
        crud = OrderCRUD(db)
        order = await crud.remove_order_item(
            order_id=request.order_id,
            product_id=request.product_id
        )
        
        logger.info("remove_item_from_order.success",
                   order_id=order.id,
                   product_id=request.product_id)
        
        return SuccessResponse(
            message="Товар успешно удален из заказа",
            data={
                "order_id": order.id,
                "order_number": order.order_number,
                "order_status": order.status,
                "order_total": float(order.total_amount),
                "product_id": request.product_id
            }
        )
        
    except OrderServiceError as e:
        logger.warning("remove_item_from_order.service_error",
                      order_id=request.order_id,
                      error=e.detail["error"])
        raise e
    except Exception as e:
        logger.error("remove_item_from_order.unexpected_error",
                    order_id=request.order_id,
                    error=str(e),
                    exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "Произошла внутренняя ошибка сервера"
            }
        )


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Получить информацию о заказе",
    description="Возвращает полную информацию о заказе с его товарами"
)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db)
) -> OrderResponse:
    """
    Получение информации о заказе.
    
    - **order_id**: ID заказа (в пути URL)
    """
    try:
        logger.info("get_order.request", order_id=order_id)
        
        crud = OrderCRUD(db)
        order = await crud.get_order_with_items(order_id)
        
        if not order:
            raise OrderNotFoundError(order_id)
        
        order_data = {
            "id": order.id,
            "order_number": order.order_number,
            "customer_id": order.customer_id,
            "customer_name": order.customer.name if order.customer else None,
            "status": order.status,
            "total_amount": order.total_amount,
            "version": order.version,
            "order_date": order.order_date,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "order_items": []
        }
        
        for item in order.order_items:
            order_data["order_items"].append({
                "id": item.id,
                "order_id": item.order_id,
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.quantity * item.unit_price,
                "created_at": item.created_at
            })
        
        logger.info("get_order.success", order_id=order_id)
        return OrderResponse(**order_data)
        
    except OrderServiceError as e:
        raise e
    except Exception as e:
        logger.error("get_order.error", order_id=order_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "Произошла внутренняя ошибка сервера"
            }
        )