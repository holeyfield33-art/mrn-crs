FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
# Install CPU-only PyTorch first to avoid pulling ~3GB of CUDA libraries
RUN pip install --no-cache-dir torch==2.3.1+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
