#!/usr/bin/env python3
"""Development wrapper for the installable ``clip.web`` command."""

from _bootstrap import SDK_ROOT  # noqa: F401
from clip.tools.web import main


if __name__ == "__main__":
    raise SystemExit(main())
