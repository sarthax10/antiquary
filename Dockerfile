FROM python:3.12-slim

# ffmpeg for pipeline/render.py; libpq for psycopg2 at runtime (psycopg2-binary already
# bundles it, but keeping this explicit doesn't hurt and matches what a non-binary
# psycopg2 would need).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY pipeline/ pipeline/
COPY migrations/ migrations/
COPY alembic.ini wsgi.py ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8787

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8787", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--timeout", "180"]
