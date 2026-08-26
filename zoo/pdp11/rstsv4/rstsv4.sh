#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

BOOT_DISK="RSTSV4A.DSK"
URL="http://www.rsts.org/autoindex.php?dir=distros/RSTS_disks/V4A/&file=RSTSV4A.DSK"

# Download the boot disk
if [ ! -f "${BOOT_DISK}" ]; then
    curl -L ${URL} -o "${BOOT_DISK}"
fi

pdp11 pdp11.ini
