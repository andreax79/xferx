#!/usr/bin/env bash
FS=rt11
DISK=V03B_Apr79/AS-5777C-BC_RT11_V03B_1-9.RX01
ARGS="$*"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
$SCRIPT_DIR/../../../xferx.py --$FS $SCRIPT_DIR/$DISK -d dl0: -c "dir $ARGS"
