#!/bin/sh
set -eu

mkdir -p "${DATA_DIR}"
chown -R appuser:appuser "${DATA_DIR}"

exec gosu appuser "$@"
