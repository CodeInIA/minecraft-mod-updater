"""Build the release changelog from the commits since the last release.

Usage: python changelog.py [LAST_VERSION]   (e.g. 2.1.0; empty = whole history)

- Merge commits are skipped.
- Commits whose subject starts with an internal prefix (tests:, release:, ci:) are skipped.
- "#minor" / "#major" markers are removed.
- "- " bullet lines of the commit body are kept as sub-items.
"""

import re
import subprocess
import sys

INTERNAL_PREFIXES = ("tests:", "test:", "release:", "ci:")
# Only a standalone marker ("... #minor"), not text such as "#minor/#major"
BUMP_MARKER = re.compile(r"\s*(?<!\S)#(minor|major)(?!\S)", re.IGNORECASE)
COMMIT_SEP, FIELD_SEP = "\x1e", "\x1f"


def commits_since(last_version: str):
    cmd = ["git", "log", "--no-merges", "--reverse", f"--format={COMMIT_SEP}%s{FIELD_SEP}%b"]
    if last_version:
        cmd.append(f"v{last_version}..HEAD")
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    for chunk in out.split(COMMIT_SEP):
        if FIELD_SEP in chunk:
            subject, body = chunk.split(FIELD_SEP, 1)
            yield subject.strip(), body


def build(commits) -> str:
    lines = []
    for subject, body in commits:
        if not subject or subject.lower().startswith(INTERNAL_PREFIXES):
            continue
        lines.append(f"- {BUMP_MARKER.sub('', subject).strip()}")
        for raw in body.splitlines():
            line = BUMP_MARKER.sub("", raw).rstrip()
            if line.lstrip().startswith("- ") and "co-authored-by" not in line.lower():
                lines.append(f"  {line.strip()}")
    if not lines:
        lines.append("- Maintenance and internal improvements.")
    return "## Novedades / What's new\n\n" + "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(build(commits_since(sys.argv[1] if len(sys.argv) > 1 else "")), end="")
