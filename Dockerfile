FROM python:3.9-slim

# Install Java
RUN apt-get update && \
    apt-get install -y default-jdk && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create upload folder
RUN mkdir -p uploads

# Add database initialization script
COPY migrations.py .
RUN python migrations.py

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV UPLOAD_FOLDER=/app/uploads

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]
