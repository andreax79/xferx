#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

URL="https://simh.trailing-edge.com/kits/xvmrsx_simh_kit.zip"

if [ ! -d "xvmrsx_simh_kit" ]; then
    URL_REL=${URL:7}
    URL_REL=${URL_REL#*/}
    URL_REL="/${URL_REL%%\?*}"
    FILENAME="${URL_REL##/*/}"
    # mv ${BOOT_DISK} ..
    curl -LO ${URL}
    unzip ${FILENAME}
    rm ${FILENAME}
fi

pdp15
