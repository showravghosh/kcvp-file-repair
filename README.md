# KCVP File Repair

A free tool that repairs files damaged by **STOP/Djvu ransomware** (`.kcvp` and the other
extensions of the same family).

It does **not** decrypt. This ransomware encrypts only the first 150 KB of each file, so most of
a large photo, song or video is still there. The tool rebuilds a usable file from that untouched
part.

- No installation on Windows: one file, double-click and use.
- Your damaged files are only read. They are never changed, moved or deleted.
- Works for every STOP/Djvu extension, not only `.kcvp`.

---

## Contents

1. [Download and start](#1-download-and-start)
2. [Before you begin](#2-before-you-begin)
3. [Step by step](#3-step-by-step)
4. [Reading the file list](#4-reading-the-file-list)
5. [What can be repaired](#5-what-can-be-repaired)
6. [What cannot be repaired](#6-what-cannot-be-repaired)
7. [iPhone HEIC photos](#7-iphone-heic-photos)
8. [Questions and answers](#8-questions-and-answers)
9. [Problems and fixes](#9-problems-and-fixes)
10. [Linux](#10-linux)
11. [How it works](#11-how-it-works)
12. [Building from source](#12-building-from-source)

---

## 1. Download and start

### Windows

1. On this page click **`KCVP_File_Repair.exe`**, then the **Download** button
   (or click the green **Code** button, choose **Download ZIP** and unzip it).
2. Double-click `KCVP_File_Repair.exe`. The window opens after a few seconds.

Nothing else is needed. The program does not install anything and does not need the internet.

**If Windows shows "Windows protected your PC":** this appears for new programs that are not
signed. Click **More info**, then **Run anyway**.

### Linux

See [section 10](#10-linux).

## 2. Before you begin

- **Clean the computer first.** Remove the ransomware with an antivirus scan or reinstall Windows.
  If it is still active, it can damage the repaired files again.
- **Keep the damaged files.** Do not delete or rename them, even after a successful repair. If the
  keys are ever published, the original files can be decrypted completely.
- **Have free space.** Repaired copies need about as much space as the damaged files.
- **Save the repaired files somewhere else.** Another folder, or better another drive. The tool
  refuses to save into the folder that holds the damaged files.

## 3. Step by step

1. **Choose what to repair.**
   Click **Folder...** to pick a folder with damaged files, or **File...** for a single file.
   Leave **Include subfolders** ticked to search all folders inside it.
2. **Choose where the repaired copies go.**
   The box **Save repaired files to** is filled in automatically with a folder ending in
   `_Repaired`. Click **Browse...** to choose another place.
3. **Click Analyze.**
   The tool finds every damaged file and checks each one. Nothing is written yet. When it
   finishes, the list shows what can be repaired and the Status box shows the totals.
4. **Click Repair.**
   Every file marked "Can be repaired" is rebuilt into the output folder, in the same folder
   layout as the originals. You can press **Stop** at any time; files already repaired are kept.
5. **Click Open output folder** and check your files.
   A report named `repair_report.csv` is saved there. It opens in Excel and lists every file with
   its result.

Large folders take time. Photos need about a second each, PNG pictures about ten seconds each,
and videos as long as it takes to copy them.

## 4. Reading the file list

| Column | Meaning |
|---|---|
| **File** | Name of the damaged file |
| **Type** | Photo, Audio, Video or Other |
| **Size** | Size of the damaged file |
| **Encrypted** | Share of the file the ransomware encrypted. Small files have a high value |
| **Recoverable** | Share of the picture, sound or video that the tool expects to bring back |
| **Details** | Whether it can be repaired, and the reason if it cannot |

Use the **Show** box above the list to see only the files that can, or cannot, be repaired.

## 5. What can be repaired

| File type | What you get |
|---|---|
| **JPEG photos** (`.jpg`, `.jpeg`) | The picture with a grey band at the top where the lost part was. Needs a file larger than about 160 KB |
| **PNG** screenshots and drawings | The lower part of the picture, exact. The upper part is lost |
| **BMP** | The picture with the bottom rows lost |
| **HEIC** (iPhone), experimental | See [section 7](#7-iphone-heic-photos) |
| **MP3, AAC, FLAC** | Plays normally, the first seconds are missing |
| **WAV** | Plays, the first second is missing |
| **MP4, 3GP, M4A, MOV** | Plays from a few seconds in |
| **VOB, MPG** (DVD video) | Plays from just after the damaged start |
| **TS, MTS, M2TS** (camcorder, TV) | Plays from just after the damaged start |
| **ZIP, JAR, APK, EPUB** | A new archive with every file that was stored after the first 150 KB |
| **DOCX, XLSX, PPTX, ODT, ODS, ODP** | A ZIP file with the parts that survive (pictures, sheets). The document itself cannot be reopened |
| **PDF** | The pages that were stored after the first 150 KB |

Things to know about the results:

- **Photos may be sideways.** The rotation information was in the lost part. Rotate them in any
  photo viewer.
- **Photo colours are estimated.** The original colour tables are lost, so a few photos can look
  slightly lighter, darker or tinted.
- **The date a photo was taken is lost**, together with the other camera information.
- **WAV files** are rebuilt as 44.1 kHz, 16 bit. If one plays too fast or too slow, the original
  used a different setting.
- **DVD video (VOB, MPG)** needs a player such as VLC. The built-in Windows player cannot play it.
- **PDF** works for documents with plain objects. Many modern PDFs store them compressed and then
  may not open.

## 6. What cannot be repaired

- **Any file smaller than 150 KB.** It is encrypted from the first byte to the last, so nothing is
  left to rebuild from. No repair tool can change this.
- **PNG photographs.** Only screenshot-like pictures come back; real photos saved as PNG do not.
- **GIF, WebP, RAR, 7z.** They cannot be read without their beginning.
- **MKV, AVI, WMV, OGG, PSD, TIFF, camera RAW.** The description of the contents was at the start.
- **JPEG photos saved by some editing apps** (custom coding tables) and progressive JPEGs.
- **MP4 and MOV files whose index was at the start.** Many downloaded videos are stored this way.

For these files:

1. Look for another copy: your phone, a memory card, WhatsApp, Messenger, email, cloud storage, or
   the person you once sent it to.
2. Try the free **Emsisoft Decryptor for STOP Djvu**. It works when the files were encrypted with
   an "offline key" that has been recovered.
3. Keep the encrypted file. If the keys are released one day, it can be decrypted.

## 7. iPhone HEIC photos

HEIC repair is experimental and needs help from you:

1. Find one **healthy** HEIC photo taken with the **same iPhone model** and the same camera
   setting (for example another photo from the phone, or from iCloud).
2. Copy it into the folder that holds the damaged HEIC photos.
3. Run Analyze and Repair as usual.

The tool takes the missing picture description from the healthy photo. Picture tiles that were
inside the encrypted part are filled with a copy of another tile, so the top of the picture will
look repeated. Without a healthy photo in the folder, HEIC files are listed as not repairable.

## 8. Questions and answers

**Does this decrypt my files?**
No. It rebuilds files from the part that was never encrypted. Nothing is decrypted and no key is
found.

**Why is 150 KB the limit?**
The ransomware encrypts exactly the first 150 KB of every file and leaves the rest alone. A file
smaller than that has no untouched part.

**Why is there a grey band on my photos?**
That is the part of the picture that was inside the encrypted 150 KB. On a large photo it is a
thin strip; on a small photo it is bigger.

**Can it harm my files?**
The damaged files are opened for reading only. The tool has no code that writes to them, renames
them or deletes them.

**Does it work for extensions other than `.kcvp`?**
Yes, for all STOP/Djvu variants. The tool recognises the files by a marker the ransomware puts at
the end of each one, not by the extension.

**Does it work for other ransomware?**
No. Other families damage files in other ways, and many encrypt the whole file.

**Should I pay the attackers?**
This is not recommended. Many victims who paid received nothing.

## 9. Problems and fixes

| Problem | What to do |
|---|---|
| "Windows protected your PC" | Click **More info**, then **Run anyway** |
| Antivirus removes the program | Add an exception for it, or build it yourself from the source |
| "No STOP/Djvu damaged files were found" | The files in that folder were not damaged by this ransomware family, or the wrong folder was chosen |
| "Choose a different folder" | The output folder is the same as the folder with the damaged files. Pick another one |
| A repaired video does not play | Try VLC. The first seconds can show a grey or broken picture |
| A repaired photo looks too light or too dark | The colour levels were estimated. Adjust brightness in a photo editor |
| The program seems stuck | Large videos and PNG pictures take time. Watch the Activity log at the bottom |

## 10. Linux

The Windows program does not run on Linux. Download this repository (green **Code** button,
**Download ZIP**), unzip it, open a terminal in the folder and run:

```
sh KCVP_File_Repair_Linux.sh
```

The first time, it installs what is missing (Python 3, Tk and a C compiler) with your system's
package manager. This needs an internet connection and may ask for your password once. After
that it starts straight away. Ubuntu, Debian, Fedora, Arch, openSUSE and Alpine are supported.

Keep the whole folder together: the Linux launcher needs the `source` folder next to it.

## 11. How it works

Every damaged file ends with the same marker, which is how the tool finds them. The first 5 bytes
are plain, the next 153,600 bytes are encrypted, and a 334 byte trailer is appended. Each file
type then has its own rebuilder:

- **JPEG.** The compressed picture data is decoded from the first intact byte. The image width is
  found from the similarity between rows, and the brightness and colour levels are estimated so
  that every pixel stays in the valid range. The picture is written back without compressing it
  again, so no quality is lost in the surviving part.
- **MP3, AAC, FLAC, DVD and camcorder video.** These are made of small independent frames. The
  tool finds the first complete frame after the damage and keeps everything from there.
- **MP4.** When the index is at the end of the file it is intact. A new header is written and the
  index is trimmed so that playback starts at the first keyframe after the damage.
- **PNG.** The compressed stream is picked up again at the next block start. Rows are kept from
  the point where they are exact again.
- **ZIP and Office files.** The directory at the end of the archive is intact, so every entry
  stored after the damage is copied into a new archive.
- **PDF.** The damaged start is blanked so the later objects keep their positions, and the page
  list is rebuilt from the pages that survive.

## 12. Building from source

Everything is in the [`source`](source) folder.

| File | Purpose |
|---|---|
| `kcvp_repair.pyw` | The window |
| `engine.py` | Finds damaged files, measures the damage, runs the repairs |
| `src/jfix.c` | The JPEG rebuilder (C) |
| `djvu_media.py`, `mp4_clean.py` | Audio and video repair |
| `png_repair.py`, `heic_repair.py`, `extra_formats.py` | The other file types |
| `build.bat`, `build.sh` | Pack everything into one program (Windows, Linux) |

Windows: install Python 3 and a C compiler (MinGW), then

```
gcc -O2 -o source\bin\jfix.exe source\src\jfix.c -lm
python -m pip install pyinstaller
source\build.bat
```

Linux: `sh source/build.sh`

To run from source without packing: `python source/kcvp_repair.pyw`

---

## Disclaimer

This tool is provided free of charge and without any warranty. Repair results differ from file to
file. Always keep your damaged original files.

## Author

Showrav Ghosh
