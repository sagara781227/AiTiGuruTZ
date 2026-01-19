from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import structlog

from src.order_service.config import settings
from src.order_service.database import engine, check_database_connection
from src.order_service.routers import orders
from src.order_service.exceptions import OrderServiceError


structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    logger.info("application.startup")
    
    db_connected = await check_database_connection()
    if not db_connected:
        logger.error("database.connection_failed")
        raise RuntimeError("Не удалось подключиться к базе данных")
    logger.info("database.connected")
    
    yield
    
    logger.info("application.shutdown")
    await engine.dispose()


app = FastAPI(
    title="Order Service API",
    description="Сервис управления заказами и товарами",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(OrderServiceError)
async def order_service_exception_handler(request, exc):
    """Обработчик ошибок сервиса заказов."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Обработчик ошибок валидации."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Ошибка валидации запроса",
            "details": exc.errors()
        }
    )


app.include_router(orders.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Проверка здоровья сервиса."""
    db_connected = await check_database_connection()
    
    if not db_connected:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "disconnected"}
        )
    
    return {"status": "healthy", "database": "connected"}


@app.get("/", tags=["root"])
async def root():
    """Корневой endpoint."""
    return {
        "service": "Order Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "order_service.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )