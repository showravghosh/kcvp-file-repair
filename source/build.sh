#!/bin/sh
# Builds the Linux program: compiles the JPEG rebuilder and packs everything into one file.
# Needs: python3, python3-tk, gcc, and PyInstaller (python3 -m pip install pyinstaller)
set -e
cd "$(dirname "$0")"
gcc -O2 -o bin/jfix src/jfix.c -lm
python3 -m PyInstaller --noconfirm --clean --onefile --windowed --name KCVP_File_Repair \
  --add-binary "bin/jfix:bin" kcvp_repair.pyw
mv -f dist/KCVP_File_Repair ../KCVP_File_Repair
rm -rf build dist
echo "Done: ../KCVP_File_Repair"
