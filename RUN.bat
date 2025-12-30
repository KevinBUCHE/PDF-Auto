@echo off
set INPUT=%1
if "%INPUT%"=="" (
  echo Usage: RUN.bat "<path to SRX*.pdf>" [--pose yes^|no] [--outdir <path>]
  exit /b 1
)
"%~dp0BDC_Generator.exe" --input "%INPUT%" %*
