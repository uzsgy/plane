#!/usr/bin/env python3
"""Split secret VPS (dotenv) into host/user/port + private key file.

Blob example:
  VPS_HOST=1.2.3.4
  VPS_USER=deploy
  VPS_PORT=22
  VPS_PRIVATE_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----\\n"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ASSIGN = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        m = ASSIGN.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if value.startswith('"') and not (value.endswith('"') and len(value) > 1):
            chunks = [value[1:]]
            while i < len(lines):
                part = lines[i]
                i += 1
                if part.endswith('"'):
                    chunks.append(part[:-1])
                    break
                chunks.append(part)
            value = "\n".join(chunks)
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        value = value.replace("\\n", "\n")
        values[key] = value
    return values


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <blob-file> <out-dir>", file=sys.stderr)
        return 2

    blob_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    text = blob_path.read_text()
    if not text.strip():
        print("VPS secret blob is empty", file=sys.stderr)
        return 1

    values = parse_dotenv(text)
    host = values.get("VPS_HOST", "").strip()
    user = values.get("VPS_USER", "").strip()
    port = values.get("VPS_PORT", "").strip()
    key = values.get("VPS_PRIVATE_KEY", "").strip() + "\n"

    if not host:
        print("Missing VPS_HOST in VPS secret", file=sys.stderr)
        return 1
    if not user:
        print("Missing VPS_USER in VPS secret", file=sys.stderr)
        return 1
    if not port:
        print("Missing VPS_PORT in VPS secret", file=sys.stderr)
        return 1
    if "PRIVATE KEY" not in key:
        print("Missing/invalid VPS_PRIVATE_KEY in VPS secret", file=sys.stderr)
        return 1

    (out_dir / "host").write_text(host + "\n")
    (out_dir / "user").write_text(user + "\n")
    (out_dir / "port").write_text(port + "\n")
    key_path = out_dir / "id_rsa"
    key_path.write_text(key)
    key_path.chmod(0o600)

    print(f"OK VPS_HOST={host} VPS_USER={user} VPS_PORT={port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
