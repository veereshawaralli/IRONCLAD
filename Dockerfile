FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY ironclad/ ./ironclad/
RUN pip install --no-cache-dir ".[production]"
COPY --from=web /web/out ./web/out
COPY examples/ ./examples/
EXPOSE 8000
CMD ["uvicorn","ironclad.api:create_app","--factory","--host","0.0.0.0","--port","8000"]
