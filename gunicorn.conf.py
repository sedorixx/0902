import multiprocessing

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
threads = 4
worker_class = 'gthread'
timeout = 300
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
worker_tmp_dir = '/dev/shm'
log_level = 'info'
