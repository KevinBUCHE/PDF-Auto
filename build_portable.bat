@echo off
setlocal
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onedir --windowed --name "BDC Generator" --add-data "Templates;Templates" main.py
endlocal
