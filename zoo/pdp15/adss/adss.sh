#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

mkdir -p tmp

BOOT_DISK="adss15_32k.dtp"
URL="http://simh.trailing-edge.com/kits/adss15.zip"

# Download the zip
if [ ! -f "tmp/adss15.zip" ]; then
    cd tmp
    curl -LO ${URL}
    unzip adss15.zip
    cd ..
fi

if [ ! -f "${BOOT_DISK}" ]; then
    cp tmp/*.dtp tmp/*.rim .
    dd if=/dev/zero of=tape1.dtp bs=591872 count=1
    dd if=/dev/zero of=tape2.dtp bs=591872 count=1
fi

pdp15
