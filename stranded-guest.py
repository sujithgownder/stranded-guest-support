"""Root CLI launcher for Stranded Guest Support."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stranded_guest_support.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
