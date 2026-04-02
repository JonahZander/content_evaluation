FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv

COPY services/api/pyproject.toml ./pyproject.toml
COPY services/api/uv.lock ./uv.lock
COPY services/api/src ./src
RUN uv sync --no-dev --frozen
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "content_evaluation.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
