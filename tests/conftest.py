import sys
from pathlib import Path

# Make `import textacad` work when running `pytest` from the project folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
