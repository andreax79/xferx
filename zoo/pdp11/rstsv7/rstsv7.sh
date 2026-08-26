#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

BOOT_DISK="rsts_full_rl.dsk"
URL="https://simh.trailing-edge.com/kits/rstsv7swre.tar.Z"

# Download the boot disk
if [ ! -f "${BOOT_DISK}" ]; then
    mkdir -p tmp
    cd tmp
    curl -LO ${URL}
    tar xf rstsv7swre.tar.Z
    mv Disks/rsts_full_rl.dsk ..
    mv Disks/rsts_swap_rl.dsk ..
    cd ..
fi

pdp11 pdp11.ini
