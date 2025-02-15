FROM python:3.9-slim

# System-Abhängigkeiten
RUN apt-get update && apt-get install -y \
    default-jre \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis erstellen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code kopieren
COPY . .

# Port freigeben
EXPOSE 8080

# Start-Command
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "app:app"]
