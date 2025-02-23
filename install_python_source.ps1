$pythonVersion = "3.11.11"
$sourceFile = "Python-$pythonVersion.tgz"
$buildDir = "Python-$pythonVersion"
$installDir = "C:\Program Files\Python311"

# Entpacke das Archiv
Write-Host "Extracting Python source..."
tar -xzf $sourceFile

# Wechsel ins Build-Verzeichnis
Set-Location $buildDir

# Konfiguriere und baue Python
Write-Host "Configuring Python build..."
./configure --prefix="$installDir" --enable-optimizations --with-ensurepip=install

Write-Host "Building Python..."
make -j8

Write-Host "Installing Python..."
make install

# Zurück zum ursprünglichen Verzeichnis
Set-Location ..

# Setze Umgebungsvariablen
$env:PATH = "$installDir;$installDir\Scripts;$env:PATH"
[Environment]::SetEnvironmentVariable("PATH", $env:PATH, [System.EnvironmentVariableTarget]::User)

# Überprüfe die Installation
Write-Host "Verifying installation..."
& "$installDir\python.exe" --version

Write-Host "Python $pythonVersion installation completed!"
