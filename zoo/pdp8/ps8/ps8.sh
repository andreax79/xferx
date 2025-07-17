#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

BOOT_DISK="ps-8-master.tu56"
URL="https://www.pdp8online.com/ftp/images/ps-8/ps-8-master.tu56"

# Download the tape
if [ ! -f "${BOOT_DISK}" ]; then
    curl -LO ${URL}
fi

pdp8 pdp8.ini
