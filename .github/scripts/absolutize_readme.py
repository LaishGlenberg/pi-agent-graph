"""Point README links at absolute URLs before building for PyPI.

PyPI renders ``README.md`` as the project description but has no repository
base URL, so relative targets such as ``./SPEC.md`` or
``docs/assets/agent-demo.gif`` resolve against ``pypi.org`` and 404. This
rewrites them against the tag being released, leaving the repository copy
untouched.

Run from the repository root with ``GITHUB_REPOSITORY`` and
``GITHUB_REF_NAME`` set.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

README = Path("README.md")

# Not already absolute, not an in-page anchor, not a scheme such as mailto:.
_RELATIVE = r"(?!https?://|#|\w+:)"
_IMAGE_SRC = re.compile(rf'src="{_RELATIVE}([^"]+)"')
_LINK_HREF = re.compile(rf"\]\({_RELATIVE}([^)]+)\)")


def _relative_targets(text: str) -> list[str]:
    """Every relative image or link target still present in ``text``."""
    return [
        match.group(1)
        for pattern in (_IMAGE_SRC, _LINK_HREF)
        for match in pattern.finditer(text)
    ]


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = os.environ["GITHUB_REF_NAME"]
    raw = f"https://raw.githubusercontent.com/{repo}/{tag}"
    blob = f"https://github.com/{repo}/blob/{tag}"

    text = README.read_text(encoding="utf-8")
    text = _IMAGE_SRC.sub(
        lambda m: f'src="{raw}/{m.group(1).removeprefix("./")}"', text
    )
    text = _LINK_HREF.sub(lambda m: f"]({blob}/{m.group(1).removeprefix('./')})", text)

    remaining = _relative_targets(text)
    if remaining:
        raise SystemExit(f"relative targets remain in README: {remaining}")

    README.write_text(text, encoding="utf-8")
    print(f"rewrote README targets against {tag}")


if __name__ == "__main__":
    main()
