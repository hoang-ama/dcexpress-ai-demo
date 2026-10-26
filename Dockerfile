# ==============================================================================
# DC EXPRESS AI AGENT - DOCKERFILE CHO FASTAPI MIDDLEWARE VÀ STREAMLIT
# ==============================================================================
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Cài đặt các gói hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Mở cổng cho FastAPI Middleware (8000) và Streamlit (8501)
EXPOSE 8000 8501

# Lệnh mặc định: Khởi động Zalo Middleware (FastAPI)
CMD ["uvicorn", "zalo_middleware:app", "--host", "0.0.0.0", "--port", "8000"]
