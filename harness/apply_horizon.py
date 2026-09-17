"""Merge two independent SRTM horizon samplings into the module.

Two samplings of the same terrain differ by where each lands relative to a
ridge crest, so the true blocking angle is the element-wise maximum. Using
the smaller of the two would let the model claim direct sun while the sun is
still behind terrain.
"""
import re

import os

P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "weather_forecast_v8_3.py")

CURRENT = [
    0.4, 1.1, 2.3, 3.0, 3.3, 3.0, 1.9, 2.5, 3.4, 3.9, 4.1, 3.9,
    3.0, 2.7, 3.2, 3.2, 3.3, 4.1, 4.1, 3.7, 3.4, 3.9, 4.3, 4.6,
    4.6, 4.1, 5.1, 5.2, 4.2, 4.0, 4.2, 4.2, 4.2, 4.0, 3.6, 3.1,
    2.6, 2.0, 1.1, 1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.4, 1.3, 1.5, 1.7, 0.9, 0.6, 0.4, 0.1, 0.5, 0.1, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
]

REGEN = [
    3.0, 3.3, 3.0, 2.4, 2.2, 1.9, 2.9, 3.4, 3.7, 4.0, 4.0, 3.7,
    3.7, 3.4, 3.0, 3.1, 3.2, 3.4, 3.8, 4.1, 4.3, 4.8, 4.9, 5.1,
    5.1, 5.4, 5.1, 4.6, 4.2, 4.2, 4.2, 4.0, 3.9, 3.7, 3.3, 3.1,
    2.8, 2.5, 1.9, 1.1, 0.7, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.3, 0.3, 0.3, 0.1, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.3, 1.9,
]

merged = [round(max(a, b), 1) for a, b in zip(CURRENT, REGEN)]

block = ["HORIZON_PROFILE_5DEG = ["]
for i in range(0, 72, 12):
    block.append("    " + ", ".join(f"{v:g}" for v in merged[i:i + 12])
                 + f",  # az {i * 5}-{i * 5 + 55}")
block.append("]")
block = "\n".join(block)

src = open(P).read()
new = re.sub(r"HORIZON_PROFILE_5DEG = \[.*?\n\]", block, src, count=1, flags=re.S)
assert new != src, "profile block not found"
open(P, "w").write(new)
print("merged profile, max =", max(merged))