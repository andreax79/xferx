#!/usr/bin/env bash
FS=cos310
DISK=cos310-v8.0.rx01
ARGS="$*"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
$SCRIPT_DIR/../../../xferx.py --$FS $SCRIPT_DIR/$DISK -d dl0: -c "dir $ARGS"
