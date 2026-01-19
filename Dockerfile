FROM python:3.11-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./

RUN uv pip install --system -r pyproject.toml

COPY src/ ./src/
COPY tests/ ./tests/

EXPOSE 8000

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "order_service.main:app", "--host", "0.0.0.0", "--port", "8000"]