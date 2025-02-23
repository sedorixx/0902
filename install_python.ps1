# Python 3.11.11 von python.org herunterladen und installieren

$pythonVersion = "3.11.11"
$downloadUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.exe"
$installerPath = ".\python_installer.exe"
$targetDir = "C:\Program Files\Python311"

Write-Host "Downloading Python $pythonVersion..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath

Write-Host "Installing Python $pythonVersion..."
Start-Process -Wait -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0", "TargetDir=$targetDir"

Write-Host "Cleaning up..."
Remove-Item $installerPath

Write-Host "Verifying installation..."
& "$targetDir\python.exe" --version

# Setze Umgebungsvariablen
$env:PATH = "$targetDir;$targetDir\Scripts;$env:PATH"
[Environment]::SetEnvironmentVariable("PATH", $env:PATH, [System.EnvironmentVariableTarget]::User)

Write-Host "Python $pythonVersion installation completed!"
