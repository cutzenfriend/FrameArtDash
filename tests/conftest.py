import sys
from pathlib import Path

# Make the fake Home Assistant helpers importable as plain modules.
sys.path.insert(0, str(Path(__file__).parent))
