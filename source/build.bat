@echo off
rem Builds KCVP_File_Repair.exe and puts it one folder up (needs: python -m pip install pyinstaller)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name KCVP_File_Repair --add-binary "bin\jfix.exe;bin" kcvp_repair.pyw
if exist dist\KCVP_File_Repair.exe move /y dist\KCVP_File_Repair.exe ..\KCVP_File_Repair.exe
rmdir /s /q build dist 2>nul
echo Done.
