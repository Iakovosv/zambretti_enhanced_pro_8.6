"""Realistic scenarios driven by pvlib clear-sky solar radiation."""
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pvlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import load, FakeDateTime  # noqa: E402

LAT, LON = 37.073583, 25.398755
TZ = "Europe/Athens"


def clearsky_ghi(dt, cloud_factor=1.0):
    ts = pd.Timestamp(dt, tz=TZ)
    cs = pvlib.location.Location(LAT, LON, tz=TZ).get_clearsky(pd.DatetimeIndex([ts]), model="ineichen")
    return max(0.0, float(cs["ghi"].iloc[0]) * cloud_factor)


def run_day(day, pressure_fn, temp_fn, hum_fn, wind_fn, cloud_factor,
            label, wind_dir=180.0, step_min=2, show_every=60):
    mod, st = load()
    import builtins; builtins.hass.config.elevation = 66.0
    st.attrs["zone.home"] = {"latitude": LAT, "longitude": LON}

    start = datetime(day.year, day.month, day.day, 0, 0)
    rows = []
    for minute in range(0, 24 * 60, step_min):
        t_now = start + timedelta(minutes=minute)
        FakeDateTime._now = t_now
        st.values["sensor.gw2000a_relative_pressure"] = pressure_fn(t_now)
        st.values["sensor.gw2000a_outdoor_temperature"] = temp_fn(t_now)
        st.values["sensor.gw2000a_humidity"] = hum_fn(t_now)
        st.values["sensor.gw2000a_wind_speed"] = wind_fn(t_now)
        st.values["sensor.gw2000a_wind_direction"] = wind_dir
        cf = cloud_factor(t_now) if callable(cloud_factor) else cloud_factor
        st.values["sensor.gw2000a_solar_radiation"] = clearsky_ghi(t_now, cf)
        mod.run()
        if minute % (show_every * step_min) == 0:
            _, val, a = st.set_calls[-1]
            rows.append((t_now.strftime("%H:%M"), val, a["forecast_atmosphere"],
                         a["sky_confidence_raw"], a["sky_confidence_persistent"],
                         a["solar_ratio"], a["expected_clear_sky"], a["solar_radiation"],
                         a["trend_3h"], a["pressure_curvature"], a["score"],
                         a["rain_probability"], a["weather_regime"],
                         a["sun_elevation"], a["sun_azimuth"], a["mountain_blocking"]))
    print(f"\n{'='*150}\n{label}\n{'='*150}")
    print(f"{'time':>5} {'forecast':<18} {'atmos':<20} {'cRaw':>5} {'cPers':>6} "
          f"{'ratio':>6} {'expSol':>7} {'solRaw':>7} {'dP3h':>6} {'curv':>6} "
          f"{'score':>5} {'rain':>5} {'regime':<13} {'elev':>6} {'az':>6} {'blk':>5}")
    for r in rows:
        print(f"{r[0]:>5} {str(r[1]):<18} {str(r[2]):<20} {r[3]:>5} {r[4]:>6} "
              f"{r[5]:>6} {r[6]:>7} {r[7]:>7} {r[8]:>6} {r[9]:>6} "
              f"{r[10]:>5} {r[11]:>5} {str(r[12]):<13} {r[13]:>6} {r[14]:>6} {r[15]:>5}")
    return rows


def summer_clear(t):
    h = t.hour + t.minute / 60
    return 1016.0, 22 + 10 * max(0, 1 - abs(h - 15) / 9), 45.0, 8.0


def winter_clear(t):
    h = t.hour + t.minute / 60
    return 1022.0, 8 + 8 * max(0, 1 - abs(h - 14) / 8), 60.0, 10.0


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("all", "summer"):
        run_day(datetime(2026, 6, 15), lambda t: summer_clear(t)[0],
                lambda t: summer_clear(t)[1], lambda t: summer_clear(t)[2],
                lambda t: summer_clear(t)[3], 1.0,
                "SCENARIO A: Καθαρή καλοκαιρινή μέρα, σταθερή υψηλή πίεση 1016 hPa")

    if which in ("all", "winter"):
        run_day(datetime(2026, 12, 15), lambda t: winter_clear(t)[0],
                lambda t: winter_clear(t)[1], lambda t: winter_clear(t)[2],
                lambda t: winter_clear(t)[3], 1.0,
                "SCENARIO B: Καθαρή χειμωνιάτικη μέρα, σταθερή πίεση 1022 hPa")
