const CACHE_NAME = 'pdf-extractor-v1';

const ASSETS_TO_CACHE = [
  '/',  
  '/upload',
  '/static/js/loading-manager.js',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
];

// Verbesserte Fehlerbehandlung für Caching
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return Promise.allSettled(
          ASSETS_TO_CACHE.map(url => 
            fetch(url)
              .then(response => {
                if (!response.ok) {
                  throw new Error('Network response was not ok');
                }
                return cache.put(url, response);
              })
              .catch(err => {
                console.warn('Failed to cache:', url, err);
              })
          )
        );
      })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        if (response) {
          return response; // Return cached version
        }
        return fetch(event.request).catch(() => {
          // Return offline fallback if fetch fails
          if (event.request.mode === 'navigate') {
            return caches.match('index.html');
          }
        });
      })
  );
});
