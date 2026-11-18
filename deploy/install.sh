#!/bin/bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root: sudo bash deploy/install.sh'; exit 1; }
command -v python3 >/dev/null || { apt-get update; apt-get install -y python3; }
cd "$(dirname "$0")/.."
exec python3 deploy/install.py
