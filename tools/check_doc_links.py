"""M0-2: check Markdown and JSON documentation destinations without networking."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def json_doc_paths(value):
    if isinstance(value, str):
        yield from re.findall(r"(?<![\w/])docs/[A-Za-z0-9_./-]+\.md", value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from json_doc_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from json_doc_paths(item)


def main():
    files = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    errors = []
    checked = 0
    for relative in sorted(set(files)):
        path = ROOT / relative
        if path.suffix == ".json" and path.is_file():
            for target in json_doc_paths(json.loads(path.read_text(encoding="utf-8"))):
                checked += 1
                if not (ROOT / target).is_file():
                    errors.append(f"{relative}: {target}")
            continue
        if path.suffix != ".md" or not path.is_file():
            continue
        # Ignore examples in fenced code; check archived links as well.
        source = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", source):
            target = unquote(target.split("#", 1)[0].strip("<>"))
            if not target or re.match(r"^[a-zA-Z][\w+.-]*:", target):
                continue
            checked += 1
            if not (path.parent / target).exists():
                errors.append(f"{relative}: {target}")
    if errors:
        raise SystemExit("Missing local link targets:\n" + "\n".join(errors))
    print(
        f"local Markdown/JSON file links: {checked} checked, no missing files (external URLs/anchors not checked)"
    )


if __name__ == "__main__":
    main()
