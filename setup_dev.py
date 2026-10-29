"""Enable the src package in the active venv without downloading build tools."""
import site
import sys
from pathlib import Path

if sys.prefix == sys.base_prefix:
    raise SystemExit("Run this with the project virtual environment's Python.")
source = Path(__file__).resolve().parent / "src"
target = Path(site.getsitepackages()[-1]) / "orion-dev.pth"
target.write_text(str(source) + "\n", encoding="utf-8")
print(f"Registered {source} in {target}")
