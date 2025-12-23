@echo off
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo %INFO%[5/6] Build PyInstaller (avec Qt runtime)...%RESET%
echo Ceci peut prendre 2-3 minutes...
echo.

python -m PyInstaller ^
    --name "BDC Generator" ^
    --onedir ^
    --windowed ^
    --noconfirm ^
    --clean ^
    --add-data "Templates;Templates" ^
    --collect-all PySide6 ^
    --collect-all shiboken6 ^
    --collect-all PyMuPDF ^
    --collect-binaries PySide6 ^
    --collect-binaries shiboken6 ^
    --collect-binaries PyMuPDF ^
    --runtime-hook hooks\runtime_qt_path.py ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=fitz ^
    main.py

if errorlevel 1 (
    echo.
    echo %ERROR%[ERREUR] Build PyInstaller echoue%RESET%
    pause
    exit /b 1
)

echo %SUCCESS%Build PyInstaller termine%RESET%
echo.

REM Copier les DLLs Qt supplémentaires
echo %INFO%[6/6] Copie des DLLs Qt...%RESET%
python scripts\copy_qt_runtime.py "dist\BDC Generator"
if errorlevel 1 (
    echo %ERROR%[ERREUR] Copie Qt echouee%RESET%
    pause
    exit /b 1
)
echo %SUCCESS%DLLs Qt copiees%RESET%
echo.

endlocal
