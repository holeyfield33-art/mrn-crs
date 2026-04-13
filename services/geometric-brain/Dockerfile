FROM python:3.11-slim

WORKDIR /app

# Clone upstream geometric-brain-mcp
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/holeyfield33-art/geometric-brain-mcp.git /repo \
    && cp -r /repo/* /app/ \
    && rm -rf /repo .git

# Install dependencies
RUN pip install --no-cache-dir -r requirements-ci.txt

# Overlay CRS adapter files
COPY self_heal.py app_wrapper.py /app/

EXPOSE 8200

CMD ["uvicorn", "app_wrapper:app", "--host", "0.0.0.0", "--port", "8200"]
