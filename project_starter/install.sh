#!/bin/bash
set -euo pipefail
# Download a fixed, reviewable project-template version. Existing gateway is untouched.
VERSION=v1.7.0
if [[ ${1:-} == --check ]]; then printf 'Project starter from %s\n' "$VERSION"; exit 0; fi
[[ $EUID -eq 0 ]] || { echo 'Run as root on Debian/Ubuntu.' >&2; exit 1; }
[[ $# -ge 2 ]] || { echo 'Usage: bash install.sh DOMAIN EMAIL [PORT]' >&2; exit 1; }
if ! command -v python3 >/dev/null; then apt-get update; apt-get install -y python3; fi
work=$(mktemp -d /tmp/link-project.XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
curl -fsSL --proto '=https' --tlsv1.2 "https://codeload.github.com/roxy-king/esp32-universal-gateway/tar.gz/refs/tags/$VERSION" -o "$work/source.tar.gz"
tar -xzf "$work/source.tar.gz" -C "$work" --strip-components=1
python3 "$work/project_starter/deploy/install.py" --domain "$1" --email "$2" --port "${3:-8767}"
