#!/usr/bin/env bash
# Load /tmp/vps (from split-vps-env.py) into ssh-agent + env vars.
set -euo pipefail

VPS_DIR="${1:-/tmp/vps}"
: "${VPS_DIR:?}"

export VPS_HOST
export VPS_USER
export VPS_PORT
VPS_HOST="$(cat "$VPS_DIR/host")"
VPS_USER="$(cat "$VPS_DIR/user")"
VPS_PORT="$(cat "$VPS_DIR/port")"

eval "$(ssh-agent -s)" >/dev/null
ssh-add "$VPS_DIR/id_rsa" >/dev/null
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keyscan -p "$VPS_PORT" -H "$VPS_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true
