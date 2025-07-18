#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

DISK1="cos310-v8.0.rx01"
URL1="https://www.pdp8online.com/ftp/images/cos/cos310-v8.0.rx01"

DISK2="cos310-v8.0-master.rx01"
URL2="https://www.pdp8online.com/ftp/images/cos/cos310-v8.0-master.rx01"

DISK3="disk1.rx01"

# Download the disks
if [ ! -f "${DISK1}" ]; then
    curl -LO ${URL1}
fi
if [ ! -f "${DISK2}" ]; then
    curl -LO ${URL2}
fi
if [ ! -f "${DISK3}" ]; then
    dd if=/dev/zero of=${DISK3} bs=256256 count=1
fi

pdp8 pdp8.ini
