#!/bin/sh
# Starts KCVP File Repair on Linux. Anything that is missing (Python 3, its window toolkit, a C compiler)
# is installed first with the system's package manager; you may be asked for your password once.
cd "$(dirname "$0")" || exit 1

need=""
command -v python3 >/dev/null 2>&1 || need="$need python"
if command -v python3 >/dev/null 2>&1; then
    python3 -c "import tkinter" >/dev/null 2>&1 || need="$need tk"
else
    need="$need tk"
fi
if [ ! -x bin/jfix ]; then
    command -v gcc >/dev/null 2>&1 || command -v cc >/dev/null 2>&1 || need="$need gcc"
fi

if [ -n "$need" ]; then
    echo "Installing what is missing:$need"
    SUDO=""
    [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get update && $SUDO apt-get install -y python3 python3-tk gcc libc6-dev
    elif command -v dnf >/dev/null 2>&1; then
        $SUDO dnf install -y python3 python3-tkinter gcc
    elif command -v yum >/dev/null 2>&1; then
        $SUDO yum install -y python3 python3-tkinter gcc
    elif command -v pacman >/dev/null 2>&1; then
        $SUDO pacman -S --needed --noconfirm python tk gcc
    elif command -v zypper >/dev/null 2>&1; then
        $SUDO zypper --non-interactive install python3 python3-tk gcc
    elif command -v apk >/dev/null 2>&1; then
        $SUDO apk add python3 python3-tkinter gcc musl-dev
    else
        echo "Could not find a package manager. Please install Python 3, Tk for Python and gcc, then run this again."
        exit 1
    fi || { echo "Installation failed. Check the internet connection and try again."; exit 1; }
fi

if [ ! -x bin/jfix ]; then
    echo "Preparing the photo rebuilder..."
    CC=gcc
    command -v gcc >/dev/null 2>&1 || CC=cc
    $CC -O2 -o bin/jfix src/jfix.c -lm || { echo "Could not compile the photo rebuilder."; exit 1; }
fi

exec python3 kcvp_repair.pyw
