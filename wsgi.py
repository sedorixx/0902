from app import app
import multiprocessing

# Gunicorn configuration
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
timeout = 300
keepalive = 5
max_requests = 1000
worker_class = 'gthread'

if __name__ == "__main__":
    app.run()
