# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim
WORKDIR /app

# System deps for LibreOffice (doc→pdf conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-impress libreoffice-calc \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY VERSION /app/VERSION

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Data directories
RUN mkdir -p /data/uploads /data/outputs /data/converted
ENV UPLOAD_DIR=/data/uploads OUTPUT_DIR=/data/outputs CONVERT_DIR=/data/converted
ENV DATABASE_URL=sqlite:////data/mineru_batch.db

EXPOSE 8900
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8900/api/stats')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8900"]
