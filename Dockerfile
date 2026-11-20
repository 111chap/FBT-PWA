FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN mkdir -p /app/data /app/media && FBT_DEBUG=1 python manage.py collectstatic --noinput && useradd --uid 10001 --no-create-home app && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["python", "serve.py"]
