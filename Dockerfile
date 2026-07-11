FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Verze se mění pouze ručně v static/version.json

EXPOSE 8000

# --proxy-headers: respektuje X-Forwarded-For za reverse proxy.
# Kterym proxy verit ridi env promenna FORWARDED_ALLOW_IPS (cte ji uvicorn),
# default "127.0.0.1" - bez nastaveni se forwarded hlavickam neveri.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

