#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

URL="https://www.pdp8online.com/ftp/images/etos/etosv5b-demo.rk05"
# URL="https://www.pdp8online.com/ftp/images/etos/etosv5b-pl5-config.rk05"
# URL="https://www.pdp8online.com/ftp/images/etos/etosv5b-pl5-dist.rk05"
BOOT_DISK="etosv5b-demo.rk05"
# BOOT_DISK="etosv5b-pl5-config.rk05"
# BOOT_DISK="etosv5b-pl5-dist.rk05"

# Download the tape
if [ ! -f "${BOOT_DISK}" ]; then
    curl -LO ${URL}
fi

pdp8 pdp8.ini
