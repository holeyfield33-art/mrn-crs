FROM python:3.11-slim

WORKDIR /app

# Clone upstream Mneme and extract the aletheia-mneme service
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/holeyfield33-art/Mneme-.git /repo \
    && cp -r /repo/aletheia-mneme/* /app/ \
    && rm -rf /repo

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Overlay CRS adapter files
COPY crs_adapter.py app_wrapper.py /app/

EXPOSE 8100

CMD ["uvicorn", "app_wrapper:app", "--host", "0.0.0.0", "--port", "8100"]
