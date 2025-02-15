FROM python:3.9-slim

# System-Abhängigkeiten und Berechtigungen
RUN apt-get update && apt-get install -y \
    default-jre \
    build-essential \
    python3-dev \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app \
    && chmod 755 /app

# Benutzer erstellen und Berechtigungen setzen
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

# Arbeitsverzeichnis setzen
WORKDIR /app

# Kopiere Requirements und installiere Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && chown appuser:appuser requirements.txt

# Kopiere App-Code
COPY . .
RUN chown -R appuser:appuser .

# Wechsle zum nicht-root Benutzer
USER appuser

# Umgebungsvariablen setzen
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.local/bin:$PATH" \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PORT=8080

# Port freigeben
EXPOSE 8080

# Start-Command
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "app:app"]
