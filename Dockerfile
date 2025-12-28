FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Vytvoříme soubor s verzí buildu
RUN python3 -c "import datetime; v = datetime.datetime.now().strftime('v.%Y%m%d.%H%M'); open('/app/static/version.json', 'w').write('{\"version\": \"' + v + '\"}')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

