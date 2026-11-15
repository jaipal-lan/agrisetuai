#!/usr/bin/env bash
# Generate a self-signed TLS cert for LOCAL HTTPS dev (so camera/scan work on a
# LAN IP). NOT for production — staging/prod use real certs via Vercel/Render.
#
# Usage:  scripts/gen-certs.sh [LAN_IP]
#   e.g.  scripts/gen-certs.sh 192.168.48.97
#
# Output: certs/cert.pem + certs/key.pem (gitignored).
set -euo pipefail

LAN_IP="${1:-192.168.48.97}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
mkdir -p "$DIR"

# Run inside the certs dir with relative filenames, and set MSYS_NO_PATHCONV so
# Git Bash (Windows) doesn't mangle the "/CN=..." subject into a path. Both are
# harmless on Linux/macOS.
(
  cd "$DIR"
  MSYS_NO_PATHCONV=1 openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout key.pem -out cert.pem \
    -subj "/CN=agrisetu-dev" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:${LAN_IP}"
)

echo "Wrote $DIR/cert.pem and $DIR/key.pem (SAN: localhost, 127.0.0.1, ${LAN_IP})"
echo "Browsers will warn once (self-signed) — accept it on each device/port."
