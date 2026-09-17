"""End-to-end regression tests for Zambretti Enhanced Pro.

These tests exercise the real module (no mocks of the forecasting logic)
against physical ground truth:
  * solar geometry vs pvlib,
  * clear-sky irradiance vs pvlib Ineichen,
  * local horizon vs an SRTM sampling,
  * pressure curvature sign,
  * absolute-pressure scoring direction,
  * dewpoint vs a trusted reference formula,
  * rain as an event (not blocked by dwell time),
  * timezone handling.

Run:  python harness/test_forecast.py
"""
import math
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pvlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import load, FakeDateTime  # noqa: E402

LAT, LON, TZ, ELEV = 37.073583, 25.398755, "Europe/Athens", 66.0

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def fresh():
    mod, st = load()
    import builtins
    builtins.hass.config.elevation = ELEV
    builtins.hass.config.time_zone = TZ
    st.attrs["zone.home"] = {"latitude": LAT, "longitude": LON}
    return mod, st


print("=" * 70)
print("1. ΘΕΣΗ ΗΛΙΟΥ vs pvlib")
print("=" * 70)
mod, _ = fresh()
worst_el = worst_az = 0.0
for day in (datetime(2026, 1, 15), datetime(2026, 4, 15),
            datetime(2026, 6, 21), datetime(2026, 9, 17),
            datetime(2026, 12, 15)):
    for hour in range(0, 24, 1):
        dt = day.replace(hour=hour, minute=0)
        sp = mod.get_solar_position_accurate(LAT, LON, dt)
        ref = pvlib.solarposition.get_solarposition(
            pd.Timestamp(dt, tz=TZ), LAT, LON
        ).iloc[0]
        worst_el = max(worst_el, abs(sp["elevation"] - float(ref["apparent_elevation"])))
        if sp["is_above_horizon"]:
            worst_az = max(worst_az, abs(sp["azimuth"] - float(ref["azimuth"])))

check("ύψος ήλιου σφάλμα < 0.5°", worst_el < 0.5, f"max={worst_el:.2f}°")
check("αζιμούθιο σφάλμα < 0.5°", worst_az < 0.5, f"max={worst_az:.2f}°")


print()
print("=" * 70)
print("2. ΚΑΘΑΡΟΣ ΟΥΡΑΝΟΣ (GHI) vs pvlib Ineichen")
print("=" * 70)
ratios = []
for day in (datetime(2026, 6, 15), datetime(2026, 9, 17), datetime(2026, 12, 15)):
    for hour in range(7, 18):
        dt = day.replace(hour=hour, minute=0)
        sp = mod.get_solar_position_accurate(LAT, LON, dt)
        blk = mod._get_local_horizon_blocking(LAT, LON, sp["azimuth"], ELEV)
        if sp["elevation"] <= blk or sp["elevation"] < 5:
            continue
        model = mod.get_expected_clear_sky_solar(LAT, LON, dt, ELEV)
        ref = float(pvlib.location.Location(LAT, LON, tz=TZ)
                    .get_clearsky(pd.DatetimeIndex([pd.Timestamp(dt, tz=TZ)]),
                                  model="ineichen")["ghi"].iloc[0])
        if ref > 50:
            ratios.append(model / ref)

check("μέσος λόγος εντός 0.95-1.15",
      0.95 <= sum(ratios) / len(ratios) <= 1.15,
      f"mean={sum(ratios)/len(ratios):.3f} n={len(ratios)}")
check("κανένας λόγος > 1.4", max(ratios) < 1.4, f"max={max(ratios):.2f}")
check("κανένας λόγος < 0.75", min(ratios) > 0.75, f"min={min(ratios):.2f}")


print()
print("=" * 70)
print("3. ΤΟΠΙΚΟΣ ΟΡΙΖΟΝΤΑΣ")
print("=" * 70)
max_blk = max(
    mod._get_local_horizon_blocking(LAT, LON, az, ELEV)
    for az in range(0, 360, 2)
)
check("μέγιστος αποκλεισμός < 8°", max_blk < 8.0, f"max={max_blk:.2f}°")
check("νότιος ορίζοντας (θάλασσα) < 1°",
      mod._get_local_horizon_blocking(LAT, LON, 200, ELEV) < 1.0,
      f"az=200 -> {mod._get_local_horizon_blocking(LAT, LON, 200, ELEV):.2f}°")
east_blk = mod._get_local_horizon_blocking(LAT, LON, 100, ELEV)
check("ανατολικός ορίζοντας 3-6°", 3.0 <= east_blk <= 6.0, f"az=100 -> {east_blk:.2f}°")


print()
print("=" * 70)
print("4. ΚΑΜΠΥΛΟΤΗΤΑ ΠΙΕΣΗΣ (πρόσημο/κανονικοποίηση)")
print("=" * 70)
now = datetime(2026, 9, 17, 12, 0)
ENTITY = "sensor.zambretti_enhanced_pro_8_4"


def curve(pressures_oldest_first):
    """Δέχεται 13 ωριαίες πιέσεις (παλαιότερη -> τρέχουσα)."""
    hist = [(now - timedelta(hours=12 - i), v)
            for i, v in enumerate(pressures_oldest_first)]
    return mod.pressure_curvature(hist, now, pressures_oldest_first[-1])


TAU = list(range(13))  # 0 = παλαιότερο, 12 = τώρα

# Σταθερή πτώση 1 hPa/h -> μηδενική καμπυλότητα
steady = curve([1018 - t for t in TAU])
check("σταθερή πτώση -> καμπυλότητα ≈ 0", abs(steady) < 0.35, f"{steady:+.2f}")

# Πτώση που ΕΠΙΤΑΧΥΝΕΤΑΙ -> αρνητική (επιδείνωση)
accel = curve([1015 - 0.12 * t * t for t in TAU])
check("επιταχυνόμενη πτώση -> αρνητική", accel < -0.2, f"{accel:+.2f}")

# Πτώση που ΕΠΙΒΡΑΔΥΝΕΤΑΙ -> θετική (βελτίωση)
decel = curve([1015 - 2.88 * t + 0.12 * t * t for t in TAU])
check("επιβραδυνόμενη πτώση -> θετική", decel > 0.2, f"{decel:+.2f}")


print()
print("=" * 70)
print("5. SCORING ΑΠΟΛΥΤΗΣ ΠΙΕΣΗΣ")
print("=" * 70)
lo = mod.score_enhanced(990, 60, 5, 0, 0, False)
hi = mod.score_enhanced(1025, 60, 5, 0, 0, False)
check("χαμηλή πίεση -> μεγαλύτερο score", lo > hi, f"990->{lo:.0f}  1025->{hi:.0f}")
check("υψηλή πίεση -> score 0 από πίεση", hi - mod.score_enhanced(1030, 60, 5, 0, 0, False) == 0)


print()
print("=" * 70)
print("6. DEWPOINT (Buck 1981)")
print("=" * 70)
# Σημείο αναφοράς: T=25°C, RH=50% -> ~13.9°C (Buck/Magnus)
dp = mod.dewpoint_depression(25.0, 50.0)
dpt = 25.0 - dp
check("T=25 RH=50 -> dewpoint ≈ 13.9°C", abs(dpt - 13.9) < 0.6, f"{dpt:.2f}°C")
dpt2 = 30.0 - mod.dewpoint_depression(30.0, 80.0)
check("T=30 RH=80 -> dewpoint ≈ 26.2°C", abs(dpt2 - 26.2) < 0.8, f"{dpt2:.2f}°C")
check("RH=100 -> dewpoint = T",
      abs(mod.dewpoint_depression(20.0, 100.0)) < 0.05)


print()
print("=" * 70)
print("7. ΖΩΝΗ ΩΡΑΣ")
print("=" * 70)
winter = mod._local_utc_offset_hours(datetime(2026, 1, 15, 12), LON)
summer = mod._local_utc_offset_hours(datetime(2026, 7, 15, 12), LON)
check("χειμώνας -> +2", abs(winter - 2.0) < 0.01, f"{winter:+.1f}")
check("καλοκαίρι -> +3", abs(summer - 3.0) < 0.01, f"{summer:+.1f}")


print()
print("=" * 70)
print("8. ΒΡΟΧΗ ΩΣ EVENT (δεν μπλοκάρεται από dwell)")
print("=" * 70)


def last_output(st):
    calls = [c for c in st.set_calls if c[0] == ENTITY]
    return calls[-1] if calls else None


def feed(st, t, p, t_c, hum, wind, solar, wdir=200.0):
    FakeDateTime._now = t
    st.values["sensor.gw2000a_relative_pressure"] = p
    st.values["sensor.gw2000a_outdoor_temperature"] = t_c
    st.values["sensor.gw2000a_humidity"] = hum
    st.values["sensor.gw2000a_wind_speed"] = wind
    st.values["sensor.gw2000a_wind_direction"] = wdir
    st.values["sensor.gw2000a_solar_radiation"] = solar


mod, st = fresh()
base = datetime(2026, 9, 17, 0, 0)


def clearsky(t):
    return float(pvlib.location.Location(LAT, LON, tz=TZ)
                 .get_clearsky(pd.DatetimeIndex([pd.Timestamp(t, tz=TZ)]),
                               model="ineichen")["ghi"].iloc[0])


for minute in range(0, 900, 2):
    t = base + timedelta(minutes=minute)
    feed(st, t, 1018.0, 24.0, 55.0, 3.0, clearsky(t))
    mod.run()
out_before = last_output(st)
check("εδραιώθηκε 'Καλός καιρός'",
      out_before[1] == "Καλός καιρός", str(out_before[1]))

# Ξαφνική καταιγίδα: πίεση καταρρέει, ήλιος σβήνει, υγρασία 95%
for minute in range(900, 960, 2):
    t = base + timedelta(minutes=minute)
    elapsed = minute - 900
    feed(st, t, 1018.0 - elapsed * 0.06, 21.0, 95.0, 12.0,
         clearsky(t) * 0.15)
    mod.run()
out_after = last_output(st)
rain_now = out_after[2]["rain_probability"]
check("η βροχή εμφανίστηκε αμέσως",
      out_after[1] in ("Βροχές", "Καταιγίδες"),
      f"{out_after[1]} (rain={rain_now})")


print()
print("=" * 70)
print("9. ΓΕΩΓΡΑΦΙΚΗ ΘΕΣΗ (get_geo)")
print("=" * 70)
mod, st = fresh()
lat, lon, elev = mod.get_geo()
check("διαβάζει τη θέση από το zone.home",
      abs(lat - LAT) < 1e-6 and abs(lon - LON) < 1e-6,
      f"{lat},{lon}")
check("διαβάζει το υψόμετρο", abs(elev - ELEV) < 1e-6, f"{elev}")


print()
print("=" * 70)
print("10. ΟΛΟΚΛΗΡΩΜΕΝΟ ΣΕΝΑΡΙΟ: καθαρή μέρα -> συννεφιά -> βροχή")
print("=" * 70)
mod, st = fresh()
base = datetime(2026, 9, 17, 0, 0)
for minute in range(0, 24 * 60, 6):
    t = base + timedelta(minutes=minute)
    h = t.hour + t.minute / 60
    p = 1018.0 if h < 12 else 1018.0 - (h - 12) * 1.8
    hum = 55.0 if h < 12 else min(98.0, 55.0 + (h - 12) * 12)
    cs = pvlib.location.Location(LAT, LON, tz=TZ).get_clearsky(
        pd.DatetimeIndex([pd.Timestamp(t, tz=TZ)]), model="ineichen")
    cloud = 0.15 if h > 13 else 1.0
    feed(st, t, p, 26.0 - max(0.0, h - 12) * 1.5, hum,
         4.0 + max(0.0, h - 12) * 2, float(cs["ghi"].iloc[0]) * cloud)
    mod.run()

out = last_output(st)
final_state = out[1]
final_rain = out[2]["rain_probability"]
final_score = out[2]["score"]
check("απόγευμα -> αυξημένη πιθανότητα βροχής",
      final_rain >= 40, f"rain={final_rain}, score={final_score}")
check("η τελική ετικέτα αντικατοπτρίζει την επιδείνωση",
      final_state in ("Βροχές", "Καταιγίδες", "Συννεφιά", "Πιθανή συννεφιά"),
      final_state)


print()
print("=" * 70)
print("11. ΚΑΘΑΡΗ ΜΕΡΑ -> 'Καλός καιρός' όλη μέρα")
print("=" * 70)
mod, st = fresh()
base = datetime(2026, 6, 20, 0, 0)
day_states = []
for minute in range(0, 24 * 60, 6):
    t = base + timedelta(minutes=minute)
    feed(st, t, 1019.0, 28.0, 45.0, 3.0, clearsky(t))
    mod.run()
    if 9 <= t.hour <= 17:
        day_states.append(last_output(st)[1])
check("ουδέποτε 'Συννεφιά' σε καθαρή μέρα",
      "Συννεφιά" not in day_states,
      f"states={sorted(set(day_states))}")
check("κυρίως 'Καλός καιρός'",
      day_states.count("Καλός καιρός") >= 0.8 * len(day_states),
      f"{day_states.count('Καλός καιρός')}/{len(day_states)}")


print()
print("=" * 70)
print("12. ΠΛΗΡΩΣ ΣΥΝΝΕΦΙΑΣΜΕΝΗ ΜΕΡΑ -> όχι 'Καλός καιρός'")
print("=" * 70)
mod, st = fresh()
overcast = []
for minute in range(0, 24 * 60, 6):
    t = base + timedelta(minutes=minute)
    feed(st, t, 1010.0, 20.0, 88.0, 8.0, clearsky(t) * 0.12)
    mod.run()
    if 9 <= t.hour <= 17:
        overcast.append(last_output(st)[1])
check("ουδέποτε 'Καλός καιρός' με πυκνή συννεφιά",
      "Καλός καιρός" not in overcast,
      f"states={sorted(set(overcast))}")
check("αναγνωρίζει συννεφιά/βροχή",
      any(s in ("Συννεφιά", "Πιθανή συννεφιά", "Βροχές", "Καταιγίδες")
          for s in overcast),
      f"states={sorted(set(overcast))}")


print()
print("=" * 70)
print(f"ΑΠΟΤΕΛΕΣΜΑ: {len(PASS)} PASS / {len(FAIL)} FAIL")
print("=" * 70)
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    sys.exit(1)
print("ΟΛΑ ΤΑ ΤΕΣΤ ΠΕΡΑΣΑΝ")