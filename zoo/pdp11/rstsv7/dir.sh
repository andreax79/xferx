#!/usr/bin/env bash
FS=rsts
DISK=rsts_full_rl.dsk
ARGS=${*:-"[1,2]"}
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
$SCRIPT_DIR/../../../xferx.py --$FS $SCRIPT_DIR/$DISK -d dl0: -c "dir $ARGS"
