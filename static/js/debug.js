/**
 * Debug-Helfer für die KI-Analyse
 */

// Aktiviere Debug-Modus durch Hinzufügen von ?debug=1 zur URL
const urlParams = new URLSearchParams(window.location.search);
const debugMode = urlParams.get('debug') === '1';

// Debug-Funktionen
const DEBUG = {
    isActive: debugMode,
    
    // Debug-Ausgabe im Konsolen-Log
    log: function(message, data) {
        if (!this.isActive) return;
        if (data) {
            console.log(`[DEBUG] ${message}`, data);
        } else {
            console.log(`[DEBUG] ${message}`);
        }
    },
    
    // Debug-Panel anzeigen
    showPanel: function() {
        if (!this.isActive) return;
        
        const debugInfo = document.getElementById('debugInfo');
        if (debugInfo) {
            debugInfo.style.display = 'block';
            
            // Füge HTTP-Methode-Tester hinzu
            const methodTester = document.createElement('div');
            methodTester.className = 'mt-3 p-2 border rounded';
            methodTester.innerHTML = `
                <h5>HTTP-Methoden Tester</h5>
                <div class="mb-2">
                    <input type="text" class="form-control mb-2" id="routeInput" value="/analyze">
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-primary test-route" data-method="GET">GET</button>
                        <button class="btn btn-sm btn-outline-primary test-route" data-method="POST">POST</button>
                        <button class="btn btn-sm btn-outline-primary test-route" data-method="PUT">PUT</button>
                        <button class="btn btn-sm btn-outline-primary test-route" data-method="DELETE">DELETE</button>
                    </div>
                </div>
                <div id="methodTesterResult" class="mt-2"></div>
            `;
            debugInfo.appendChild(methodTester);
            
            // Event-Listener für die Buttons
            document.querySelectorAll('.test-route').forEach(button => {
                button.addEventListener('click', () => {
                    const route = document.getElementById('routeInput').value;
                    const method = button.getAttribute('data-method');
                    this.testRouteMethod(route, method);
                });
            });
        }
    },
    
    // Route mit verschiedenen Methoden testen
    testRouteMethod: function(route, method) {
        if (!this.isActive) return;
        
        this.log(`Testing route ${route} with method ${method}`);
        const resultElement = document.getElementById('methodTesterResult');
        
        if (resultElement) {
            resultElement.innerHTML = `<div class="alert alert-info">Testing ${method} ${route}...</div>`;
        }
        
        fetch(route, { method: method })
            .then(response => {
                const status = response.status;
                const statusText = response.statusText;
                
                this.log(`Route ${route} ${method} response: ${status} ${statusText}`);
                
                if (resultElement) {
                    const alertClass = status >= 200 && status < 300 ? 'alert-success' : 'alert-warning';
                    resultElement.innerHTML = `
                        <div class="alert ${alertClass}">
                            <strong>Status:</strong> ${status} ${statusText}<br>
                            <small>Headers: ${JSON.stringify(Object.fromEntries(response.headers))}</small>
                        </div>
                    `;
                }
                
                return response.text();
            })
            .then(data => {
                this.log(`Response data (truncated):`, data.substring(0, 100) + '...');
                if (resultElement) {
                    const existingHtml = resultElement.innerHTML;
                    resultElement.innerHTML = `${existingHtml}<div class="border p-2 mt-2" style="max-height:200px;overflow:auto;"><pre>${data.substring(0, 500)}...</pre></div>`;
                }
            })
            .catch(error => {
                this.log(`Error testing route ${route} with method ${method}:`, error);
                if (resultElement) {
                    resultElement.innerHTML = `<div class="alert alert-danger">Error: ${error}</div>`;
                }
            });
    },
    
    // Bestehende testRoute-Methode 
    testRoute: function(route, callback) {
        if (!this.isActive) return;
        
        this.log(`Testing route: ${route}`);
        
        fetch(route)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.text();
            })
            .then(data => {
                this.log(`Route ${route} successful:`, data.substring(0, 100) + '...');
                if (callback) callback(true, data);
            })
            .catch(error => {
                this.log(`Route ${route} failed:`, error);
                if (callback) callback(false, error);
            });
    }
};

// Initialisiere Debug-Funktionen wenn im Debug-Modus
document.addEventListener('DOMContentLoaded', function() {
    if (DEBUG.isActive) {
        DEBUG.log('Debug mode active');
        DEBUG.showPanel();
        
        // Füge diese Informationen dem Debug-Panel hinzu
        const debugInfo = document.getElementById('debugInfo');
        if (debugInfo) {
            debugInfo.innerHTML += `
                <div class="mt-2">
                    <p><strong>Browser Info:</strong> ${navigator.userAgent}</p>
                    <p><strong>URL:</strong> ${window.location.href}</p>
                    <p><strong>Current path:</strong> ${window.location.pathname}</p>
                    <p><strong>Query params:</strong> ${window.location.search}</p>
                </div>
            `;
            
            // Aktuellen HTTP-Status hinzufügen
            const fetchStatus = () => {
                fetch('/status', { method: 'GET' })
                    .then(response => {
                        debugInfo.innerHTML += `
                            <div class="alert alert-info">
                                <strong>Server Status:</strong> ${response.status} ${response.statusText}
                            </div>
                        `;
                    })
                    .catch(error => {
                        debugInfo.innerHTML += `
                            <div class="alert alert-danger">
                                <strong>Server Status:</strong> Error: ${error.message}
                            </div>
                        `;
                    });
            };
            
            // Füge Button zum Erkunden der Routen hinzu
            const exploreButton = document.createElement('button');
            exploreButton.className = 'btn btn-sm btn-secondary mt-2';
            exploreButton.textContent = 'Routen erkunden';
            exploreButton.addEventListener('click', () => {
                DEBUG.testRoute('/');
                DEBUG.testRoute('/extract');
                DEBUG.testRoute('/list_files');
                const pathname = window.location.pathname;
                if (pathname && pathname !== '/') {
                    DEBUG.testRoute(pathname);
                }
            });
            debugInfo.appendChild(exploreButton);
        }
    }
});
