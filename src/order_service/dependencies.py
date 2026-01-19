from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator
from typing import Optional

from src.order_service.database import AsyncSessionLocal
from src.order_service.config import settings


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость для получения сессии БД."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> None:
    """Проверка API ключа (опционально)."""
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )