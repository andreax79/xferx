#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

BOOT_DISK="s1s2unix_rf.img"
URL="https://github.com/TheBrokenPipe/Research-UNIX-V2-Beta/raw/refs/heads/main/s1s2unix_rf.img"

# Download the boot disk
if [ ! -f "${BOOT_DISK}" ]; then
    curl -LO ${URL}
fi

pdp11 pdp11.ini
