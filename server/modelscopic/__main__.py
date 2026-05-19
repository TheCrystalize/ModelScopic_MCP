"""Entry point for `python -m modelscopic`."""

from __future__ import annotations

import asyncio

from .server import run_stdio


def main() -> None:
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
