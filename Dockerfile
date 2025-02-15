FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    default-jdk \
    build-essential \
    python3-dev \
    libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install numpy first
RUN pip install --no-cache-dir numpy==1.21.0

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create upload folder
RUN mkdir -p uploads

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV UPLOAD_FOLDER=/app/uploads

# Expose port
EXPOSE 5000

# Initialize database and create tables
RUN flask db init && \
    flask db migrate && \
    flask db upgrade

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]
