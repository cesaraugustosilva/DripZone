import subprocess
import sys
from pathlib import Path


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend)


if __name__ == "__main__":
    main()
