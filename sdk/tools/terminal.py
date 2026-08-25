#!/usr/bin/env python3
"""Development wrapper for the installable ``clip.terminal`` command."""

from _bootstrap import SDK_ROOT  # noqa: F401
from clip.tools.terminal import main


if __name__ == "__main__":
    raise SystemExit(main())
