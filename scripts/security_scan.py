from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED_SUFFIXES = {".py", ".toml", ".yml", ".yaml", ".json", ".env", ".bat"}
EXCLUDED = {Path("scripts/security_scan.py")}
PATTERNS = {
    "secret assignment": re.compile(
        r"(?i)(private" + r"[_-]?key|mnemonic|seed[ _-]?phrase|wallet[ _-]?secret)\s*[:=]\s*[^\s$<{]+"
    ),
    "authorization material": re.compile(r"(?i)(authorization|cookie)\s*:\s*(bearer|[^\s$<{]{12,})"),
    "real order method": re.compile(r"(?i)(createandpost" + r"order|post[_-]?order|sign[_-]?order)"),
    "bypass logic": re.compile(r"(?i)(geo[_-]?bypass|rotate[_-]?proxy|vpn[_-]?bypass)"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False)
    paths = (
        [Path(line) for line in result.stdout.splitlines()]
        if result.returncode == 0 and result.stdout
        else [p.relative_to(ROOT) for p in ROOT.rglob("*") if p.is_file()]
    )
    return [path for path in paths if path.suffix.lower() in SCANNED_SUFFIXES and path not in EXCLUDED]


def main() -> int:
    findings: list[str] = []
    for relative in tracked_files():
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative.as_posix()}:{line}: {label}")
    ignored = subprocess.run(
        ["git", "check-ignore", ".env", ".venv/runtime", "data/scanner.db", "logs/scanner.jsonl"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if ignored.returncode not in (0, 1) or len(ignored.stdout.splitlines()) < 4:
        findings.append(".gitignore does not cover all runtime-sensitive paths")
    if findings:
        print("SECURITY SCAN FAILED")
        print("\n".join(findings))
        return 1
    print("SECURITY SCAN PASSED: no secret assignments, signing, order submission, or bypass logic found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
