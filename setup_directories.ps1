# Prüfe Python-Version und setze Pfad
$pythonExe = "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.11.exe"
if (Test-Path $pythonExe) {
    $env:PATH = "$env:LOCALAPPDATA\Microsoft\WindowsApps;$env:PATH"
} else {
    Write-Host "Python 3.11 nicht gefunden. Bitte führen Sie zuerst install_python_win.ps1 aus."
    exit 1
}

# Environment Variables
$env:SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL = "True"
$env:PIP_NO_CACHE_DIR = "true"

# Erstelle virtuelle Umgebung mit Python 3.11
Remove-Item -Recurse -Force venv -ErrorAction SilentlyContinue
& $pythonExe -m venv venv
.\venv\Scripts\Activate

$directories = @(
    "training_data",
    "models",
    "reprocess",
    "training/models"
)

foreach ($dir in $directories) {
    New-Item -ItemType Directory -Path $dir -Force
    Write-Host "Created directory: $dir"
}

# Basis-Setup mit korrektem Python-Pfad
Write-Host "Upgrading pip, setuptools, and wheel..."
& "$pwd\venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel

# Separate Installation der kritischen Pakete mit korrektem Python-Pfad
$critical_packages = @(
    "pip==23.2.1",
    "setuptools==68.0.0",
    "wheel==0.41.1",
    "numpy==1.24.3"
)

foreach ($package in $critical_packages) {
    Write-Host "Installing $package..."
    & "$pwd\venv\Scripts\python.exe" -m pip install --no-deps $package
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error installing $package"
        exit 1
    }
}

# Installiere rest der Pakete mit korrektem Python-Pfad
Write-Host "Installing packages from requirements.txt..."
& "$pwd\venv\Scripts\python.exe" -m pip install -r requirements.txt --no-cache-dir

# Überprüfe kritische Installationen
$check_packages = @(
    @{Name="numpy"; Import="numpy"; VersionAttr="__version__"},
    @{Name="scikit-learn"; Import="sklearn"; VersionAttr="__version__"},
    @{Name="torch"; Import="torch"; VersionAttr="__version__"}
)

foreach ($package in $check_packages) {
    python -c "import $($package.Import); print(f'$($package.Name) version: {$($package.Import).$($package.VersionAttr)}')"
}

# Überprüfung der Installation
python test_sklearn.py

# Erstelle .env Datei falls nicht vorhanden
if (-not(Test-Path -Path ".env")) {
    @"
DATABASE_URL=sqlite:///app.db
FLASK_APP=main.py
FLASK_ENV=development
"@ | Out-File -FilePath ".env" -Encoding UTF8
}
