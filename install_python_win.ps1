$pythonVersion = "3.11.0"
# Microsoft Store Download URL
$downloadUrl = "https://apps.microsoft.com/store/detail/python-311/9NRWMJP3717K"
$installDir = "$env:USERPROFILE\AppData\Local\Programs\Python311"

try {
    # Öffne Microsoft Store für Python Installation
    Write-Host "Opening Microsoft Store for Python $pythonVersion installation..."
    Start-Process "ms-windows-store://pdp/?productid=9NRWMJP3717K"
    
    Write-Host "Please install Python 3.11 from the Microsoft Store."
    Write-Host "Press any key after the installation is complete..."
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')

    # Warte kurz, bis die Installation abgeschlossen ist
    Start-Sleep -Seconds 5

    # Überprüfe Installation
    $pythonExe = "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.11.exe"
    if (Test-Path $pythonExe) {
        Write-Host "Verifying Python installation..."
        & $pythonExe --version
        
        # Setze Umgebungsvariablen
        $newPath = "$env:LOCALAPPDATA\Microsoft\WindowsApps;" + [Environment]::GetEnvironmentVariable("PATH", "User")
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
        $env:PATH = $newPath
        
        Write-Host "Python installation completed!"
    } else {
        throw "Python executable not found at: $pythonExe"
    }

} catch {
    Write-Host "Error during installation: $_" -ForegroundColor Red
    exit 1
}

# Aktualisiere PowerShell-Sitzung
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
