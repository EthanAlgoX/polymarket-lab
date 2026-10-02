FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PMS_HOST=0.0.0.0 PMS_PORT=8000
WORKDIR /app
RUN addgroup --system scanner && adduser --system --ingroup scanner scanner
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY app ./app
RUN mkdir -p data logs && chown -R scanner:scanner /app
USER scanner
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD python -c "import urllib.request; from app.config import get_settings; urllib.request.urlopen('http://127.0.0.1:' + str(get_settings().port) + '/health', timeout=3)"
STOPSIGNAL SIGTERM
CMD ["python", "-m", "app"]
