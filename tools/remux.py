"""Remux a MediaRecorder WebM for playback: `python tools/remux.py <src> <dst>`.

A command-line door onto engine_contract.prepare_playback, so a Node check
(verify_playback.mjs --control) can produce exactly the file the researcher
app would serve, through the same function rather than a copy of it.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))

from engine_contract.media import prepare_playback  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: remux.py <src> <dst>")
    print(prepare_playback(sys.argv[1], sys.argv[2]))
