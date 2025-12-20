@echo off
setlocal
if not exist dist_installer\BDC_Generator_Setup_User.exe (
  echo Missing installer. Run build_installer.bat first.
  exit /b 1
)
if not exist README_Installation.txt (
  echo Missing README_Installation.txt
  exit /b 1
)
if exist BDC_Generator.zip del BDC_Generator.zip
mkdir release_zip
copy dist_installer\BDC_Generator_Setup_User.exe release_zip\
copy README_Installation.txt release_zip\
cd release_zip
powershell -Command "Compress-Archive -Path * -DestinationPath ..\\BDC_Generator.zip"
cd ..
rmdir /s /q release_zip
endlocal
