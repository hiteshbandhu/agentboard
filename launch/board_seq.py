"""Renders the board as an animation, one PNG per frame of the TUI, for the
film: the spinner turns, glints sweep across working cards, data refreshes.

  python3 launch/board_seq.py [frames]   -> launch/out/seq/board_0000.png …

The board redraws every 90 ms and refreshes data every 2 s, so frame i is
HALLMONITOR_FRAME=i on demo tick 400 + i // 22.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import assets

N = int(sys.argv[1]) if len(sys.argv) > 1 else 48
HERE = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(HERE, "out", "seq")
os.makedirs(SEQ, exist_ok=True)
assets.OUT = SEQ
xdg = os.path.join(HERE, "out", "xdg")
assets.fake_ledger(xdg)
home = os.path.join(HERE, "out", "home")
os.makedirs(home, exist_ok=True)
base = {"XDG_DATA_HOME": xdg, "HOME": home, "HALLMONITOR_HOSTNAME": "macbook-pro", "HALLMONITOR_NO_PROBE": "1"}


def one(i):
    env = dict(base, HALLMONITOR_DEMO_TICKS=str(400 + i // 22), HALLMONITOR_FRAME=str(i))
    return assets.render(["--demo"], (172, 50), f"board_{i:04d}", env)


with ThreadPoolExecutor(4) as ex:
    for p in ex.map(one, range(N)):
        print(p, flush=True)
assets.render(["--demo", "--view", "usage"], (172, 50), "usage", base)
