FROM python:3.11-slim

# System deps: Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-ara \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY versions.json .
COPY setup_admin.py .

# Create data directory for SQLite
RUN mkdir -p /app/data

ENV DATABASE_URL=sqlite+aiosqlite:///./data/screen_translator.db
ENV VERSIONS_FILE=/app/versions.json

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
