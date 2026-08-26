#!/usr/bin/env bash
FS=unix1
DISK=s1s2unix_rf.img
ARGS="${*}"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
$SCRIPT_DIR/../../xferx.py --$FS $SCRIPT_DIR/$DISK -d dl0: -c "dir $ARGS"
