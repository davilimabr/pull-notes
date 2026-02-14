"""Entry point for ``python -m pullnotes``."""

from .cli import run


def main() -> int:
    """Execute CLI workflow."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
