param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path "$PSScriptRoot/.."
Set-Location $repoRoot

Write-Host "Installing dependencies" -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade pip | Out-Null
& $PythonExe -m pip install -r requirements-dev.txt

Write-Host "Running tests" -ForegroundColor Cyan
& $PythonExe -m pytest

Write-Host "Building portable bundle" -ForegroundColor Cyan
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
& $PythonExe -m PyInstaller --noconfirm --onedir --name BDC_Generator main.py

$bundleDir = Join-Path $repoRoot "dist/BDC_Generator"
if (!(Test-Path $bundleDir)) {
    throw "Bundle output not found at $bundleDir"
}

Copy-Item -Path (Join-Path $repoRoot "Templates/bon de commande V1.pdf") -Destination $bundleDir -Force
Copy-Item -Path (Join-Path $repoRoot "config.json") -Destination $bundleDir -Force
Copy-Item -Path (Join-Path $repoRoot "RUN.bat") -Destination $bundleDir -Force
New-Item -ItemType Directory -Force -Path (Join-Path $bundleDir "BDC_Output") | Out-Null

Write-Host "Portable build ready in $bundleDir" -ForegroundColor Green
