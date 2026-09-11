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
COPY tests/ tests/
COPY alembic.ini wsgi.py ./

# Caption fonts (pipeline/captions.py) — the base image only ships DejaVu, so every
# caption silently fell back to it regardless of the .ass style's requested font name.
# These are OFL-licensed (pipeline/assets/fonts/OFL.txt), free for commercial use.
RUN mkdir -p /usr/share/fonts/truetype/antiquary \
    && cp pipeline/assets/fonts/*.ttf /usr/share/fonts/truetype/antiquary/ \
    && fc-cache -f

ENV PYTHONUNBUFFERED=1
EXPOSE 8787

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8787", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--timeout", "180"]
