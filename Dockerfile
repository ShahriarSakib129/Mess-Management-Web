FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=3000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 3000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-3000} --workers 2 --threads 4 --timeout 120 run:app"]
