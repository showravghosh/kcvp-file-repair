KCVP File Repair 1.3.0
======================

Repairs files damaged by STOP/Djvu ransomware (.kcvp and the other extensions of the same
family). It rebuilds a usable file from the part that was not encrypted. It does not
decrypt anything.

How to use
----------
1. Start dist\KCVP_File_Repair.exe (or run kcvp_repair.pyw with Python 3).
2. Choose a folder or a single damaged file.
3. Choose the folder where the repaired copies should be saved.
4. Press Analyze. The list shows, for every file, how much is encrypted and how much
   can be recovered.
5. Press Repair. A report (repair_report.csv) is written to the output folder.

The damaged files are only read. They are never changed, moved or deleted. Keep them:
if the keys are ever published they can be decrypted completely.

What can be repaired
--------------------
JPEG photos        larger than about 160 KB. A grey band at the top marks the lost part.
                   Colours and contrast are estimated. Rotation information is lost.
BMP pictures       24 bit, uncompressed. The bottom rows are lost.
PNG pictures       screenshots and drawings only: the lower part of the picture is
                   restored exactly, the upper part is lost. Photographs saved as PNG
                   cannot be rebuilt and are refused. Slow: several seconds per picture.
HEIC photos        iPhone photos (experimental). Put one healthy HEIC photo from the same
                   iPhone model and camera setting into the folder of the damaged ones;
                   it is used as a template. Lost picture tiles are filled with a copy.
MP3, AAC, FLAC     the first seconds are missing.
WAV                the first second is missing. The sound format is assumed to be
                   44.1 kHz, 16 bit.
MP4, 3GP, M4A, MOV when the index is at the end of the file. Playback starts a few
                   seconds in.
VOB, MPG           plays from just after the damaged start.
TS, MTS, M2TS      camcorder and TV recordings; plays from just after the damaged start.
ZIP, JAR, APK,     every file stored after the first 150 KB of the archive is recovered
EPUB               into a new archive.
DOCX, XLSX, PPTX,  the document itself cannot be reopened, but the internal parts that
ODT, ODS, ODP      survive (pictures, sheets, text parts) are saved as a ZIP file.
PDF                pages stored after the first 150 KB. The page list is rebuilt when it
                   was lost. Works for PDFs with plain objects; many modern PDFs keep
                   them compressed and then only open if their index survived.

What cannot be repaired
-----------------------
- Any file smaller than 150 KB: it is encrypted completely.
- GIF, WebP: one compressed stream that cannot be read without its beginning.
- PNG photographs (see above).
- Camera RAW, PSD, TIFF: the layout tables at the start are lost.
- MKV, AVI, WMV, OGG: the stream description at the start is lost.
- RAR, 7z: solid archives cannot be read from the middle.
- JPEG photos saved with custom coding tables, and progressive JPEGs.
- MP4/MOV files whose index was at the start of the file.

Tested
------
JPEG, MP3, AAC, MP4, 3GP, VOB and MPG were tested on several thousand really damaged files.
BMP on one real file, PNG on real damaged screenshots. TS, M2TS, WAV, FLAC, ZIP, DOCX and PDF were tested on healthy files
damaged in the same way as the ransomware does it, not yet on real victims' files.

Linux
-----
The Windows program does not run on Linux. Copy the whole tool folder to the Linux machine and run

    sh KCVP_File_Repair_Linux.sh

The first time, it installs anything that is missing (Python 3, Tk, a C compiler) with the
system's package manager, which needs an internet connection and may ask for your password.
After that it starts straight away. A single program file can be built with:  sh source/build.sh

Windows needs nothing: KCVP_File_Repair.exe contains everything.

Building from source
--------------------
src/jfix.c is the JPEG rebuilder.
Windows:  gcc -O2 -o bin\jfix.exe src\jfix.c -lm     then build.bat
Linux:    sh build.sh
Both scripts pack everything into one program with PyInstaller and put it one folder up.
