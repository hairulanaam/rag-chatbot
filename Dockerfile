FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (agar Docker cache efektif)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh project ke dalam container
COPY . .

# Buat folder data (untuk temp files saat indexing)
RUN mkdir -p /app/data

# HF Spaces menggunakan port 7860
EXPOSE 7860

# Jalankan server
CMD ["uvicorn", "main_server:app", "--host", "0.0.0.0", "--port", "7860"]
