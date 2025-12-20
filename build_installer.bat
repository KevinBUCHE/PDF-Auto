@echo off
setlocal
call build_portable.bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\bdc_generator.iss
endlocal
