"""Entry point embedded in the standalone macOS app."""

from sift.bridge import main


if __name__ == "__main__":
    raise SystemExit(main())
