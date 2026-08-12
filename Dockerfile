FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["python", "scripts/container_entrypoint.py"]
