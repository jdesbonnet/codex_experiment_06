#!/usr/bin/env bash
set -euo pipefail

if [[ ! -e /dev/usbtmc0 ]]; then
  echo "No /dev/usbtmc0 found. Is the usbtmc kernel driver loaded?" >&2
  exit 1
fi

cat /dev/usbtmc0
