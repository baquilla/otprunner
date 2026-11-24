#!/usr/bin/env python3
"""Check commit messages against Conventional Commits (https://www.conventionalcommits.org).

scripts/check-commits.py <file>          # commit-msg hook: the message file
scripts/check-commits.py --range A..B    # CI: every commit in a git range
"""

from __future__ import annotations

import re
import subprocess
import sys

TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert")
PATTERN = re.compile(rf"^({'|'.join(TYPES)})(\([a-z0-9._-]+\))?!?: \S.{{0,98}}$")
SKIP = re.compile(r"^(Merge |Revert \"|fixup! |squash! )")


def check(subject: str) -> str | None:
    if SKIP.match(subject) or PATTERN.match(subject):
        return None
    expected = f"<type>(<scope>)?: <summary>, type in {', '.join(TYPES)}"
    return f"not a Conventional Commit: {subject!r}\n  expected: {expected}"


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--range":
        out = subprocess.run(["git", "log", "--format=%s", argv[1]], capture_output=True, text=True, check=True)
        subjects = [s for s in out.stdout.splitlines() if s]
    elif len(argv) == 1:
        with open(argv[0], encoding="utf-8") as f:
            subjects = [next((line for line in f if line.strip() and not line.startswith("#")), "").rstrip("\n")]
    else:
        print(__doc__, file=sys.stderr)
        return 2
    errors = [e for e in map(check, subjects) if e]
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
