#!/bin/bash
set -e
# Set the current working directory to the directory of this script
cd "$(dirname "$0")"

BOOT_DISK="dosv2a_4p.rf"
URL="http://simh.trailing-edge.com/kits/dos15.zip"

# Download the boot disk
if [ ! -f "${BOOT_DISK}" ]; then
    mkdir -p tmp
    cd tmp
    URL_REL=${URL:7}
    URL_REL=${URL_REL#*/}
    URL_REL="/${URL_REL%%\?*}"
    FILENAME="${URL_REL##/*/}"
    curl -LO ${URL}
    unzip ${FILENAME}
    mv ${BOOT_DISK} ..
    mv rfsboot.rim ..
    mv checkout.bt ..
    mv per.dta ..
    mv readme.txt ..
    cd ..
    # rm -rf tmp
fi

pdp15 pdp15.ini
