"""Fail closed when a required research experiment is missing or failed."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def verify(paths: list[str]) -> list[str]:
    failures: list[str] = []
    if not paths:
        return ["No experiment results supplied."]
    for name in paths:
        path = Path(name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            failures.append(f"{name}: cannot load result: {exc}")
            continue
        checks = data.get("acceptance")
        if not isinstance(checks, dict) or not checks:
            failures.append(f"{name}: missing/nonempty acceptance object required")
            continue
        for key, value in checks.items():
            if type(value) is not bool:
                failures.append(f"{name}: {key} must be a JSON boolean, got {value!r}")
            elif not value:
                failures.append(f"{name}: {key} = false")
    return failures


def main() -> int:
    failures = verify(sys.argv[1:])
    if failures:
        for failure in failures:
            print("FAIL:", failure, file=sys.stderr)
        return 1
    print(f"PASS: {len(sys.argv) - 1} experiment acceptance files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
