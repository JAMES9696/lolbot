#!/usr/bin/env python3
"""Lightweight secret/PII scanner (SAST-lite) for CI gate.

Scans tracked files for common secret patterns and PII leaks.
This is NOT a replacement for professional tools, but acts as a fast
prevention layer in CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = {
    "riot_api_key": re.compile(r"RGAPI-[0-9A-Fa-f\-]{20,}"),
    "discord_token": re.compile(r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}"),
    "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic_key": re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"].{12,}"),
}


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return findings
    for name, pat in PATTERNS.items():
        for m in pat.finditer(text):
            findings.append(f"{name}:{path}:{m.start()}..{m.end()}")
    return findings


def main() -> int:
    root = Path.cwd()
    findings: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.suffix in {".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4", ".pdf"}:
            continue
        findings.extend(scan_file(p))
    if findings:
        print("Potential secrets/PII found:")
        for f in findings[:50]:
            print(" -", f)
        return 1
    print("No secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
