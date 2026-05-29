# KarmaForge Dockerfile — multi-stage build: frontend + backend
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

# System deps: libgomp1 for scipy, ca-certificates for HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] sqlalchemy pyjwt pydantic bcrypt python-dotenv \
    openai scipy scikit-learn pandas numpy nltk textstat pyyaml tqdm click

COPY src/ src/
COPY config.yaml .
COPY --from=frontend-build /frontend/dist/ src/static/

RUN mkdir -p data/processed data/tracking data/generations

EXPOSE 8001

CMD ["sh", "-c", "echo 'Starting KarmaForge on port' ${PORT:-8001} && uvicorn karmaforge.api.main:app --host 0.0.0.0 --port ${PORT:-8001} --log-level info"]
