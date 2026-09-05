FROM python:3.12-slim

WORKDIR /app

# Sekolah di WITA (UTC+8); container default UTC. Logika bisnis sudah pakai
# app/services/waktu.hari_ini() (offset tetap, tanpa tzdata), TZ di sini
# hanya biar log & `date.today()` OS ikut WITA.
ENV TZ=Asia/Makassar

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
