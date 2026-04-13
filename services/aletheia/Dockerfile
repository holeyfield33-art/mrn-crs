FROM python:3.11-slim

WORKDIR /app

# Clone upstream aletheia-core
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/holeyfield33-art/aletheia-core.git /repo \
    && cp -r /repo/* /app/ \
    && rm -rf /repo

# Install dependencies (upstream uses --require-hashes; we relax for compat)
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir fastapi uvicorn pydantic httpx structlog

# Create data + cache directories before dropping privileges
RUN mkdir -p /app/data /app/.cache \
    && touch /app/audit.log \
    && chown -R nobody:nogroup /app/data /app/.cache /app/audit.log

ENV HF_HOME=/app/.cache
ENV TRANSFORMERS_CACHE=/app/.cache

USER nobody

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "bridge.fastapi_wrapper:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "5"]
