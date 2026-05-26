from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Sequence


def shell_join(parts: Sequence[str], platform: str | None = None) -> str:
    """Render an argv vector for the host shell without using shell execution."""
    values = [str(part) for part in parts]
    if (platform or os.name) == "nt":
        return subprocess.list2cmdline(values)
    return shlex.join(values)
