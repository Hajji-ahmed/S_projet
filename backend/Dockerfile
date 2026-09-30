# Image de développement. L'image de production (multi-stage, utilisateur non-root) viendra en P19.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dépendances d'abord : cette couche est mise en cache tant que pyproject.toml ne change pas
COPY pyproject.toml ./
COPY app/__init__.py ./app/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
