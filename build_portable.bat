@echo off
setlocal
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onedir --windowed --name "BDC Generator" --add-data "Templates;Templates" --hidden-import=winrt --hidden-import=winrt.windows.media.ocr --hidden-import=winrt.windows.graphics.imaging --hidden-import=winrt.windows.storage.streams main.py
endlocal
