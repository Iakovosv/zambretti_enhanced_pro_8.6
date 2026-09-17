"""Measure the local horizon profile from SRTM 90 m for a station.

Samples a polar grid around the station, corrects each sample for Earth
curvature and standard atmospheric refraction (effective radius 7/6 R),
and reports the maximum blocking angle per 5-degree azimuth sector.

Usage:
    python harness/build_horizon_profile.py 37.073583 25.398755 66
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request

LAT = float(sys.argv[1]) if len(sys.argv) > 1 else 37.073583
LON = float(sys.argv[2]) if len(sys.argv) > 2 else 25.398755
ELEV = float(sys.argv[3]) if len(sys.argv) > 3 else 66.0

DISTANCES_KM = [0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 25.0]
R_EFF = 6371000.0 * 7 / 6


def fetch(points):
    locs = "|".join(f"{a},{b}" for a, b in points)
    url = "https://api.opentopodata.org/v1/srtm90m?" + urllib.parse.urlencode(
        {"locations": locs}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "zambretti-horizon"})
    for _ in range(6):
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if d.get("status") == "OK":
                return [r["elevation"] for r in d["results"]]
        except Exception as exc:
            print("   retry:", exc, flush=True)
        time.sleep(4)
    raise SystemExit("opentopodata failed")


pts = []
for az in range(0, 360):
    for d in DISTANCES_KM:
        br = math.radians(az)
        dlat = (d / 111.32) * math.cos(br)
        dlon = (d / (111.32 * math.cos(math.radians(LAT)))) * math.sin(br)
        pts.append((az, d, round(LAT + dlat, 6), round(LON + dlon, 6)))

elevs = []
for i in range(0, len(pts), 100):
    elevs.extend(fetch([(p[2], p[3]) for p in pts[i:i + 100]]))
    time.sleep(1.0)

by_az = {}
for (az, dist, _, _), e in zip(pts, elevs):
    drop = (dist * 1000.0) ** 2 / (2 * R_EFF)
    ang = math.degrees(math.atan2(e - ELEV - drop, dist * 1000.0))
    by_az[az] = max(by_az.get(az, -90.0), ang)

profile = []
for start in range(0, 360, 5):
    profile.append(round(max(0.0, max(by_az[a] for a in range(start, start + 5))), 1))

print("HORIZON_PROFILE_5DEG = [")
for i in range(0, 72, 12):
    print("    " + ", ".join(f"{v:g}" for v in profile[i:i + 12])
          + f",  # az {i * 5}-{i * 5 + 55}")
print("]")
print("\nmax blocking:", max(profile), "deg")