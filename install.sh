#!/bin/bash
# Public bootstrap; the source version is fixed for reproducible installation.
set -euo pipefail
REPOSITORY='roxy-king/esp32-universal-gateway'
VERSION='v1.4.0'
if [[ ${1:-} == --check ]]; then
    printf 'Repository: %s\nVersion: %s\n' "$REPOSITORY" "$VERSION"
    exit 0
fi
[[ $EUID -eq 0 ]] || { echo 'Please log in as root before running this command.' >&2; exit 1; }
[[ -r /etc/debian_version ]] || { echo 'Debian/Ubuntu required.' >&2; exit 1; }
[[ -r /dev/tty ]] || { echo 'Run in an interactive SSH terminal.' >&2; exit 1; }
if ! command -v curl >/dev/null || ! command -v tar >/dev/null; then
    apt-get update
    apt-get install -y ca-certificates curl tar
fi
workdir=$(mktemp -d /tmp/esp-gateway-public.XXXXXXXX)
trap 'rm -rf -- "$workdir"' EXIT
printf 'Downloading %s %s ...\n' "$REPOSITORY" "$VERSION"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --retry 3 --connect-timeout 20 --max-time 180 \
    "https://codeload.github.com/$REPOSITORY/tar.gz/refs/tags/$VERSION" -o "$workdir/source.tar.gz"
tar -xzf "$workdir/source.tar.gz" -C "$workdir" --strip-components=1
[[ -f "$workdir/deploy/install.sh" && -f "$workdir/server/server.py" ]] || { echo 'Incomplete source archive.' >&2; exit 1; }
# Explicit terminal input also works if this bootstrap was invoked through a pipe.
bash "$workdir/deploy/install.sh" </dev/tty
