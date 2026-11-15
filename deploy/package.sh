#!/usr/bin/env bash
# Build both frontends and package only runtime code/data, excluding local secrets and macOS metadata.
set -euo pipefail
cd "$(dirname "$0")/.."
output=${1:-/tmp/roco-deploy.tar.gz}
npm --prefix web run build
VITE_PUBLIC_ONLY=1 npm --prefix web run build -- --outDir dist-public
COPYFILE_DISABLE=1 tar --no-xattrs --exclude='._*' --exclude='__pycache__' --exclude='*.pyc' \
    -czf "$output" requirements.txt roco_agent roco_data roco_server scripts \
    data/bwiki/converted data/bwiki/modules data/bwiki/image_urls.json data/mechanics \
    web/dist web/dist-public deploy
printf 'Deployment bundle: %s\n' "$output"
