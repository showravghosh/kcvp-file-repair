# KCVP File Repair

A free tool that repairs files damaged by **STOP/Djvu ransomware** (`.kcvp` and the other
extensions of the same family).

It does **not** decrypt. This ransomware encrypts only the first 150 KB of each file, so most of
a large photo, song or video is still there. The tool rebuilds a usable file from that untouched
part.

## What to expect

| File type | Result |
|---|---|
| JPEG photos | Picture restored with a grey band at the top (the lost part) |
| PNG screenshots and drawings | Lower part of the picture restored |
| BMP | Picture restored, bottom rows lost |
| HEIC (iPhone), experimental | Needs one healthy photo from the same iPhone in the same folder |
| MP3, AAC, FLAC, WAV | Plays, first seconds missing |
| MP4, 3GP, M4A, MOV | Plays from a few seconds in (when the index is at the end of the file) |
| VOB, MPG, TS, MTS, M2TS | Plays from just after the damaged start |
| ZIP, JAR, APK, EPUB | New archive with every file stored after the first 150 KB |
| DOCX, XLSX, PPTX, ODT | Surviving internal parts (pictures, sheets) saved as a ZIP |
| PDF | Pages stored after the first 150 KB |

**Cannot be repaired:** any file smaller than 150 KB (it is encrypted completely), GIF, WebP,
RAR, 7z, MKV, AVI, WMV, photos saved with custom coding tables, and MP4 files whose index was at
the start. For these, look for another copy of the file and keep the encrypted one in case the
keys are published one day.

## How to use

**Windows:** download `KCVP_File_Repair.exe` from the
[Releases](../../releases) page and double-click it. Nothing needs to be installed.

**Linux:** download the source and run `sh KCVP_File_Repair_Linux.sh`. The first run installs
Python 3, Tk and a C compiler if they are missing.

1. Choose a folder or a single damaged file.
2. Choose where the repaired copies should be saved.
3. Press **Analyze** to see, for every file, how much is encrypted and how much can be recovered.
4. Press **Repair**. A report (`repair_report.csv`) is written to the output folder.

## Safety

- The damaged files are only read. They are never changed, moved or deleted.
- Repaired copies are always written to a different folder.
- Clean the infected computer before you use it again, and work on a copy of your files if you can.
- Keep the encrypted originals. If the keys are ever released, they can be decrypted completely.

## How it works

Every damaged file ends with the same marker, which is how the tool recognises them whatever the
extension is. The first 5 bytes are plain, the next 153,600 bytes are encrypted, and a 334 byte
trailer is appended. Each file type then has its own rebuilder, for example:

- **JPEG:** the entropy-coded picture data is decoded from the first intact byte, the image width
  is found from row-to-row similarity, and brightness and colour levels are estimated so that every
  pixel stays in range. The picture is written back without re-compressing it.
- **MP4:** a new header is written and the index is trimmed so playback starts at the first
  keyframe after the damage.
- **PNG:** the compressed stream is picked up again at the next block start, and rows are kept from
  the point where they become exact again.

## Building

Source is in [`source/`](source). `source/build.bat` (Windows) and `source/build.sh` (Linux) pack
it into a single program with PyInstaller. The JPEG rebuilder is `source/src/jfix.c`.

## Author

Showrav Ghosh
