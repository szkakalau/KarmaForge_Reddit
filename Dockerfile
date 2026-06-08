# KarmaForge Dockerfile — multi-stage: frontend + backend
# Stage 1: Build React frontend
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + static serving
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 ca-certificates gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] sqlalchemy pyjwt pydantic bcrypt python-dotenv passlib \
    openai scipy scikit-learn pandas numpy nltk textstat pyyaml tqdm click httpx \
    stripe alembic psycopg2-binary

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY data/patterns/ data/patterns/
COPY --from=frontend-build /frontend/dist/ src/static/

RUN mkdir -p data/processed data/tracking data/generations

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn karmaforge.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]
