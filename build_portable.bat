@echo off
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller --noconfirm --clean --onedir --windowed --name "BDC Generator" ^
  --add-data "Templates;Templates" ^
  --collect-all PySide6 ^
  --collect-all shiboken6 ^
  --runtime-hook hooks\runtime_qt_path.py ^
  --hidden-import=winrt ^
  --hidden-import=winrt.windows.media.ocr ^
  --hidden-import=winrt.windows.graphics.imaging ^
  --hidden-import=winrt.windows.storage.streams ^
  main.py

endlocal
