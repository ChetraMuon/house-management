#!/bin/sh
# Prepare the persistent volume used for the SQLite database and product images.
set -e

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/uploads/products"

exec "$@"
