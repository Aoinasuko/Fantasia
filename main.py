from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fantasia.crashlog import install_crash_logging

install_crash_logging()

from fantasia.app import main


if __name__ == "__main__":
    main()
