FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY turnos ./turnos
COPY db ./db
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 turnos

USER turnos
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"
CMD ["uvicorn", "turnos.api:app", "--host", "0.0.0.0", "--port", "8000"]
