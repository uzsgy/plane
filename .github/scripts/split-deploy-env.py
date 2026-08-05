#!/usr/bin/env python3
"""Split one APP_ENV_* secret blob into deploy meta + plane.env.

Blob format (dotenv):
  DEPLOY_PATH=/path/on/vps/for/compose
  APP_DOMAIN=plane.example.com
  SECRET_KEY=...
  # + full Plane variables.env keys
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

META_KEYS = {"DEPLOY_PATH"}
ASSIGN = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines; supports values in double quotes with \\n escapes."""
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
        values[key] = value
    return values


def write_dotenv(path: Path, items: dict[str, str]) -> None:
    lines: list[str] = []
    for key, value in items.items():
        if "\n" in value or value.startswith('"') or " " in value or value == "":
            escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <blob-file> <out-dir>", file=sys.stderr)
        return 2

    blob_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    text = blob_path.read_text()
    if not text.strip():
        print("APP_ENV blob is empty — set secret APP_ENV_STAGING / APP_ENV_PRODUCTION", file=sys.stderr)
        return 1

    values = parse_dotenv(text)
    deploy_path = values.get("DEPLOY_PATH", "").strip()
    if not deploy_path:
        print("Missing DEPLOY_PATH in APP_ENV blob", file=sys.stderr)
        return 1

    app_domain = values.get("APP_DOMAIN", "").strip()
    if not app_domain:
        print("Missing APP_DOMAIN in APP_ENV blob", file=sys.stderr)
        return 1

    secret_key = values.get("SECRET_KEY", "").strip()
    if not secret_key:
        print("Missing SECRET_KEY in APP_ENV blob", file=sys.stderr)
        return 1

    plane_env = {k: v for k, v in values.items() if k not in META_KEYS}

    (out_dir / "deploy_path").write_text(deploy_path + "\n")
    write_dotenv(out_dir / "plane.env", plane_env)

    print(f"OK deploy_path={deploy_path}")
    print(f"OK APP_DOMAIN={app_domain}")
    print(f"OK plane env keys={len(plane_env)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
