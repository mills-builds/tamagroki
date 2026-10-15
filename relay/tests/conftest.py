import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# mock xAI VAD uses raw peak level; keep mic gain neutral in tests
import os as _os
_os.environ.setdefault("RELAY_IN_GAIN", "1")
