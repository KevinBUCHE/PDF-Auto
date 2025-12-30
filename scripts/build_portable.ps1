param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$distPath = Join-Path $OutputDir "BDC Generator"
python -m PyInstaller `
    --name "BDC Generator" `
    --onedir `
    --windowed `
    --noconfirm `
    --clean `
    main.py

New-Item -ItemType Directory -Force -Path (Join-Path $distPath "Templates") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $distPath "logs") | Out-Null

$zipPath = Join-Path $OutputDir "bdc-generator-portable.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath
}
Compress-Archive -Path $distPath -DestinationPath $zipPath -Force
Write-Host "Portable build ready:" $zipPath
