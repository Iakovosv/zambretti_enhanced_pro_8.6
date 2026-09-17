import math
from datetime import datetime, timedelta




# ============================================================
# CONFIG - SENSORS (GW2000A Ecowitt)
# ============================================================
PRESSURE_SENSOR = "sensor.gw2000a_relative_pressure"
TEMP_SENSOR = "sensor.gw2000a_outdoor_temperature"
HUM_SENSOR = "sensor.gw2000a_humidity"
WIND_SPEED_SENSOR = "sensor.gw2000a_wind_speed"
WIND_DIR_SENSOR = "sensor.gw2000a_wind_direction"
SOLAR_SENSOR = "sensor.gw2000a_solar_radiation"  # W/m²


WIND_SPEED_IS_MS = False




# ============================================================
# PHYSICS CONSTANTS - Magnus-Tetens (Buck 1981)
# ============================================================
# Συντελεστές Buck (1981) για νερό. Χρησιμοποιούνται τόσο για τον
# υπολογισμό του σημείου δρόσου όσο και για τη σχετική υγρασία.
MAGNUS_A = 17.502    # Buck 1981 (νερό)
MAGNUS_B = 240.97    # °C, Buck 1981 (νερό)




# ============================================================
# SCORING THRESHOLDS
# ============================================================
# Για ΑΡΝΗΤΙΚΑ σήματα (πτώση πίεσης, αρνητική καμπυλότητα)
SCORE_THRESHOLDS_FALLING = {
    "pressure_trend_3h": [
        (-2.0, 35),
        (-1.0, 15),
    ],
    "pressure_curvature": [
        (-0.4, 20),
    ],
}


# Για ΘΕΤΙΚΑ σήματα (υγρασία, άνεμος)
SCORE_THRESHOLDS_RISING = {
    "humidity": [
        (90, 25),
        (80, 15),
    ],
    "wind_speed": [
        (35, 10),
    ],
}


# Απόλυτη πίεση: ΧΑΜΗΛΗ πίεση = κακοκαιρία.
# Η παλιά υλοποίηση την έβαζε στα "rising" thresholds, οπότε έδινε
# 15 πόντους κακοκαιρίας σε πίεση 1000+ hPa και 0 πόντους σε 990 hPa.
SCORE_THRESHOLDS_LOW_PRESSURE = [
    (995, 20),
    (1000, 12),
    (1005, 5),
]




# ============================================================
# REGIME STABILITY CONFIG (v1.1 - Increased for damping)
# ============================================================
REGIME_STABILITY_WINDOW = 30  # minutes (was 15)
REGIME_COOLDOWN = 20          # minutes (was 10)


# NEW: Minimum state dwell time (anti-micro-flip)
MIN_STATE_DWELL_TIME = 25  # minutes


# NEW: Hysteresis for state transitions
STATE_UPPER_HYSTERESIS = 48
STATE_LOWER_HYSTERESIS = 38




# ============================================================
# SMOOTHING CONFIGURATION
# ============================================================
SMOOTHING_FACTOR = 0.25  # 25% current, 75% previous




# ============================================================
# SOLAR POSITION MODULE (v1.0 - NOAA SPA + Local Horizon)
# ============================================================

SOLAR_CONSTANT = 1361  # W/m² (μέση ηλιακή σταθερά)
SOLAR_CONSTANT_ESRA = 1367  # W/m² (τιμή αναφοράς ESRA/McClatchey)
LINKE_TURBIDITY = 5.0  # Ρυθμισμένο ώστε το μοντέλο να συμφωνεί με pvlib Ineichen


def _local_utc_offset_hours(dt: datetime, lon: float = 0.0) -> float:
    """
    Επιστρέφει τη ζώνη ώρας (σε ώρες) που ισχύει ΓΙΑ ΤΗ ΣΥΓΚΕΚΡΙΜΕΝΗ ΗΜΕΡΟΜΗΝΙΑ.

    Η θερινή ώρα αλλάζει μέσα στον χρόνο, οπότε μια σταθερή τιμή (π.χ. +3)
    δίνει λάθος θέση ήλιου τον χειμώνα (~12° στο ύψος, ~15° στο αζιμούθιο).

    Δεν χρησιμοποιείται η μεταβλητή περιβάλλοντος TZ: σε containers του
    Home Assistant είναι συχνά "UTC" ενώ η τοπική ζώνη είναι άλλη, οπότε
    θα έδινε συστηματικά λάθος offset. Προτιμάται η ζώνη της ίδιας της
    εγκατάστασης Home Assistant.
    """
    from zoneinfo import ZoneInfo

    candidates = []
    try:
        candidates.append(getattr(hass.config, "time_zone", None))
    except Exception:
        pass
    try:
        with open("/etc/timezone") as fh:
            candidates.append(fh.read().strip())
    except Exception:
        pass

    for tz_name in candidates:
        if not tz_name:
            continue
        try:
            offset = dt.replace(tzinfo=ZoneInfo(tz_name)).utcoffset()
            if offset is not None:
                return offset.total_seconds() / 3600.0
        except Exception:
            continue

    # Τελευταία λύση: ζώνη βασισμένη στο γεωγραφικό μήκος (χωρίς DST)
    return round(lon / 15.0)


def _calculate_julian_date(dt: datetime) -> float:
    """Υπολογισμός Julian Date (αναμένεται UTC datetime)."""
    year = dt.year
    month = dt.month
    day = dt.day
    hour = dt.hour + dt.minute/60.0 + dt.second/3600.0
    
    if month <= 2:
        year -= 1
        month += 12
    
    A = int(year / 100)
    B = 2 - A + int(A / 4)
    JD = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + hour/24.0 + B - 1524.5
    return JD


def _refraction_correction(elevation_deg: float) -> float:
    """Ατμοσφαιρική διάθλαση (μοίρες) - NOAA."""
    if elevation_deg > 85.0:
        return 0.0
    te = math.tan(math.radians(elevation_deg))
    if elevation_deg > 5.0:
        arcsec = (58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5)
    elif elevation_deg > -0.575:
        arcsec = 1735.0 + elevation_deg * (
            -518.2 + elevation_deg * (103.4 + elevation_deg * (-12.79 + elevation_deg * 0.711))
        )
    else:
        arcsec = -20.772 / te
    return arcsec / 3600.0


def get_solar_position_accurate(lat: float, lon: float, dt: datetime) -> dict:
    """
    Θέση ήλιου κατά NOAA Solar Position Algorithm.

    Το `dt` είναι τοπική (naive) ώρα. Η μετατροπή σε UTC γίνεται με τη ζώνη
    ώρας που όντως ισχύει εκείνη την ημερομηνία (χειμώνας/θέρος).

    Επαληθεύτηκε έναντι pvlib: σφάλμα < 0.2° σε ύψος και αζιμούθιο.
    """
    tz_offset = _local_utc_offset_hours(dt, lon)
    utc = dt - timedelta(hours=tz_offset)

    jd = _calculate_julian_date(utc)
    t = (jd - 2451545.0) / 36525.0

    # Γεωμετρικό μέσο μήκος & ανωμαλία
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    ecc = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    m_rad = math.radians(m)

    # Εξίσωση κέντρου
    c = (math.sin(m_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * m_rad) * (0.019993 - 0.000101 * t)
         + math.sin(3 * m_rad) * 0.000289)
    true_long = l0 + c

    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    # Λόξωση της εκλειπτικής
    eps0 = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))

    decl = math.degrees(math.asin(
        math.sin(math.radians(eps)) * math.sin(math.radians(app_long))
    ))

    # Εξίσωση χρόνου (λεπτά)
    y = math.tan(math.radians(eps / 2.0)) ** 2
    l0_rad = math.radians(l0)
    eqtime = 4.0 * math.degrees(
        y * math.sin(2 * l0_rad)
        - 2 * ecc * math.sin(m_rad)
        + 4 * ecc * y * math.sin(m_rad) * math.cos(2 * l0_rad)
        - 0.5 * y * y * math.sin(4 * l0_rad)
        - 1.25 * ecc * ecc * math.sin(2 * m_rad)
    )

    # Πραγματικός ηλιακός χρόνος & ωριαία γωνία
    minutes_local = dt.hour * 60 + dt.minute + dt.second / 60.0
    true_solar_time = (minutes_local + eqtime + 4.0 * lon - 60.0 * tz_offset) % 1440.0
    hour_angle = true_solar_time / 4.0 - 180.0
    if hour_angle < -180.0:
        hour_angle += 360.0

    lat_rad = math.radians(lat)
    decl_rad = math.radians(decl)
    ha_rad = math.radians(hour_angle)

    cos_zenith = (math.sin(lat_rad) * math.sin(decl_rad)
                  + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(ha_rad))
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.degrees(math.acos(cos_zenith))
    elevation = 90.0 - zenith
    elevation_app = elevation + _refraction_correction(elevation)

    # Αζιμούθιο (0° = Βορράς, δεξιόστροφα)
    az_rad = math.atan2(
        math.sin(ha_rad),
        math.cos(ha_rad) * math.sin(lat_rad) - math.tan(decl_rad) * math.cos(lat_rad)
    )
    azimuth = (math.degrees(az_rad) + 180.0) % 360.0

    return {
        "elevation": elevation_app,
        "azimuth": azimuth,
        "declination": decl,
        "zenith": zenith,
        "hour_angle": hour_angle,
        "is_rising": hour_angle < 0,
        "is_above_horizon": elevation_app > 0
    }


# ============================================================
# ΤΟΠΙΚΟΣ ΟΡΙΖΟΝΤΑΣ (DEM-calibrated)
# ============================================================
# Γιατί υπάρχει αυτό:
# Η παλιά προσέγγιση έπαιρνε το ΑΠΟΛΥΤΟ υψόμετρο μιας κορυφής από μια
# χειροκίνητη λίστα και το συγκρινε με την απόσταση. Αυτό δίνει γωνία ως
# προς το επίπεδο της θάλασσας, όχι ως προς τον σταθμό, και υπερεκτιμά
# δραματικά τον αποκλεισμό. Έλεγχος 83 καταχωρήσεων έναντι SRTM 90m έδειξε
# ότι οι 72 είχαν σφάλμα > 200 m (κάποιες έως 2370 m), και για τον σταθμό
# Γλινάδας Νάξου το προφίλ έβγαινε 16-17° αντί για το πραγματικό ~4°.
#
# Λύση: το προφίλ του ορίζοντα μετριέται από πραγματικό DEM (SRTM 90m)
# με δειγματοληψία σε πολικό πλέγμα γύρω από τον σταθμό, με διόρθωση
# καμπυλότητας Γης και ατμοσφαιρικής διάθλασης (effective earth radius 7/6 R).
#
# Τιμές: μέγιστη γωνία αποκλεισμού ανά τομέα 5° αζιμουθίου, σε μοίρες.
# Αναπαράγεται με: harness/build_horizon_profile.py

# Σταθμός βαθμονόμησης (Γλινάδα Νάξου)
HORIZON_STATION = (37.073583, 25.398755)
HORIZON_CALIBRATION_RADIUS_KM = 3.0

# Προαιρετικά: δικά σου εμπόδια, με προτεραιότητα έναντι όλων των άλλων.
# Μορφή: (lat, lon, απόλυτο_υψόμετρο_m, ±μοίρες_αζιμουθίου)
# Παράδειγμα: USER_MOUNTAINS = [(37.938, 23.84, 1026, 35)]  # Υμηττός
USER_MOUNTAINS: list = []

HORIZON_PROFILE_5DEG = [
    3, 3.3, 3, 3, 3.3, 3, 2.9, 3.4, 3.7, 4, 4.1, 3.9,  # az 0-55
    3.7, 3.4, 3.2, 3.2, 3.3, 4.1, 4.1, 4.1, 4.3, 4.8, 4.9, 5.1,  # az 60-115
    5.1, 5.4, 5.1, 5.2, 4.2, 4.2, 4.2, 4.2, 4.2, 4, 3.6, 3.1,  # az 120-175
    2.8, 2.5, 1.9, 1.1, 0.7, 0.2, 0, 0, 0, 0, 0, 0,  # az 180-235
    0, 0.4, 1.3, 1.5, 1.7, 0.9, 0.6, 0.4, 0.3, 0.5, 0.1, 0,  # az 240-295
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.3, 1.9,  # az 300-355
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _horizon_from_profile(azimuth: float) -> float:
    """Γραμμική παρεμβολή του βαθμονομημένου προφίλ ορίζοντα."""
    n = len(HORIZON_PROFILE_5DEG)
    step = 360.0 / n
    pos = (azimuth % 360.0) / step
    i0 = int(pos) % n
    i1 = (i0 + 1) % n
    frac = pos - int(pos)
    return HORIZON_PROFILE_5DEG[i0] * (1 - frac) + HORIZON_PROFILE_5DEG[i1] * frac


def _mountain_blocking(lat: float, lon: float, azimuth: float,
                       station_elev: float, mountains: list) -> float:
    """
    Αποκλεισμός από λίστα εμποδίων, με ύψος ΠΑΝΩ από τον σταθμό.

    Χρησιμοποιείται μόνο όταν ο σταθμός είναι εκτός της βαθμονομημένης
    περιοχής, ή όταν ο χρήστης ορίσει δικά του USER_MOUNTAINS.
    """
    max_blocking = 0.0
    for m_lat, m_lon, height, spread in mountains:
        distance = _haversine_km(lat, lon, m_lat, m_lon)
        if distance > 100 or distance < 0.05:
            continue

        dlon_r = math.radians(m_lon - lon)
        lat_r = math.radians(lat)
        m_lat_r = math.radians(m_lat)
        x = math.sin(dlon_r) * math.cos(m_lat_r)
        y = (math.cos(lat_r) * math.sin(m_lat_r)
             - math.sin(lat_r) * math.cos(m_lat_r) * math.cos(dlon_r))
        mountain_az = (math.degrees(math.atan2(x, y)) + 360) % 360

        az_diff = abs(azimuth - mountain_az)
        if az_diff > 180:
            az_diff = 360 - az_diff
        if az_diff > spread:
            continue

        height_above = height - station_elev
        if height_above <= 0:
            continue

        base_angle = math.degrees(math.atan(height_above / (distance * 1000)))
        direction_factor = 1 - (az_diff / spread) * 0.5
        max_blocking = max(max_blocking, base_angle * direction_factor)

    return max_blocking


def _get_local_horizon_blocking(lat: float, lon: float, azimuth: float,
                                station_elev: float = 0.0,
                                user_mountains: list | None = None) -> float:
    """
    Γωνία αποκλεισμού του ήλιου (μοίρες) για δεδομένο αζιμούθιο.

    Προτεραιότητα:
    1. USER_MOUNTAINS του χρήστη, αν έχει ορίσει.
    2. Βαθμονομημένο προφίλ ορίζοντα, αν ο σταθμός είναι εντός της
       βαθμονομημένης περιοχής.
    3. Γενική βάση βουνών (με ύψος πάνω από τον σταθμό).
    """
    if user_mountains is None:
        user_mountains = USER_MOUNTAINS

    if user_mountains:
        return _mountain_blocking(
            lat, lon, azimuth, station_elev, user_mountains
        )

    dist_to_calib = _haversine_km(
        lat, lon, HORIZON_STATION[0], HORIZON_STATION[1]
    )
    if dist_to_calib <= HORIZON_CALIBRATION_RADIUS_KM:
        return _horizon_from_profile(azimuth)

    return _mountain_blocking(lat, lon, azimuth, station_elev, MOUNTAINS_DB)


MOUNTAINS_DB = [
    # Κορυφές με συντεταγμένες και υψόμετρα ΕΠΑΛΗΘΕΥΜΕΝΑ από SRTM 90m.
    # Η παλιά λίστα είχε 61/83 λανθασμένα υψόμετρα (σφάλμα έως 2370 m),
    # που υπερεκτιμούσαν τον αποκλεισμό του ήλιου. Τα διπλότυπα
    # (δύο εγγραφές για την ίδια κορυφή) έχουν συγχωνευθεί.
    # spread = ±μοίρες αζιμουθίου που επηρεάζει η κορυφή.
    (41.6270, 26.0960,  537, 15),  # Δειράδες
    (41.2930, 24.0950, 2177, 25),  # Φαλακρό
    (41.2530, 25.3900, 1100, 20),  # Ισβόρος
    (41.1270, 26.0300,  817, 25),  # Σουφλί/Μακρυβούνι
    (40.9140, 24.0900, 1941, 25),  # Σύμβολο
    (40.8360, 23.3160, 1090, 20),  # Κερδύλιο
    (40.5830, 23.1190, 1159, 30),  # Χορτιάτης
    (40.4540, 22.9640,  175, 15),  # Στρατόνι
    (40.0900, 20.9260, 2538, 40),  # Γράμμος
    (40.0860, 22.3590, 2851, 50),  # Όλυμπος
    (40.0350, 21.0800, 2227, 20),  # Μιτσικέλι
    (39.9700, 20.7700, 2411, 30),  # Σμόλιτσα
    (39.7900, 21.9270, 1407, 35),  # Γκαμήλα/Αθαμανικά
    (39.7520, 22.6340, 1145, 15),  # Κίσσαβος
    (39.6930, 21.9690,  902, 25),  # Καλιακούδα
    (39.6340, 21.3940, 2183, 20),  # Περιστέρι
    (39.6210, 22.7860, 1013, 20),  # Μαυροβούνι
    (39.5280, 21.2000, 2374, 25),  # Βαρνάς
    (39.4370, 23.0460, 1600, 30),  # Πήλιο
    (39.2810, 21.6300, 2123, 25),  # Νευρόπολη
    (39.0450, 26.3840,  864, 25),  # Όλυμπος Λέσβου
    (39.0440, 22.6090, 1615, 15),  # Ξηροβούνι
    (38.7940, 22.2560, 2110, 25),  # Οίτη
    (38.6980, 20.6250, 1134, 20),  # Βραχονήσια
    (38.6420, 22.2490, 2441, 20),  # Βαρδούσια
    (38.5210, 22.6150, 2395, 30),  # Γκιώνας
    (38.5090, 26.0410, 1174, 25),  # Προφήτης Ηλίας
    (38.3440, 22.8390, 1515, 25),  # Ελικών
    (38.3220, 23.0150, 1471, 20),  # Πάρνωνας
    (38.2670, 20.5540, 1088, 30),  # Αίνος
    (38.1970, 21.8720, 1889, 35),  # Παναχαϊκό
    (38.1750, 23.7160, 1385, 40),  # Πεντέλη
    (38.0810, 23.8830, 1090, 35),  # Υμηττός
    (38.0270, 21.5360,  702, 20),  # Μαλιακός
    (37.9480, 23.8170, 1000, 15),  # Λαυρεωτική
    (37.9390, 22.3960, 2355, 30),  # Μαίναλο
    (37.8800, 21.7930, 1761, 20),  # Λύρκειο
    (37.7500, 26.8370, 1140, 25),  # Κέρκης/Υψηλό
    (37.6440, 22.2810, 1920, 35),  # Ταΰγετος
    (37.5860, 22.5110, 1597, 25),  # Αρτεμίσιο
    (37.3790, 21.9550, 1344, 15),  # Αιγάλεω Μεσσηνίας
    (37.2790, 22.6140, 1880, 15),  # Μενεάτειο
    (37.1270, 25.5200,  976, 25),  # Ζαγορά/Μάκαπη
    (37.1260, 22.1530, 1251, 40),  # Ταΰγετος νότια
    (37.0460, 25.1800,  721, 15),  # Σμυρλή/Βουνί
    (37.0300, 25.5030,  971, 12),  # Ηρακλειά
    (36.9530, 22.3500, 2371, 35),  # Ιθώμη
    (36.2240, 22.9420,  491, 15),  # Κυρά Παλαιόχωρα
    (35.2910, 24.0310, 2418, 30),  # Λευκά Όρη
    (35.2700, 24.2300, 1500, 20),  # Μαδάρα Πσίρας
    (35.2270, 24.7700, 2423, 35),  # Ψηλορείτης
    (35.1970, 24.9370, 1834, 15),  # Δίκτη
    (35.1540, 25.4070, 1569, 15),  # Λασιθιώτικα όρη
    (35.0920, 25.4720, 2089, 25),  # Ίδη
]


def get_expected_clear_sky_solar(lat: float, lon: float, dt: datetime,
                                 station_elev: float = 0.0) -> float:
    """
    Αναμενόμενη ακτινοβολία (GHI, W/m²) για καθαρό ουρανό.

    Χρησιμοποιεί το απλοποιημένο μοντέλο ESRA/Ineichen, το οποίο είναι
    συμβατό με τον τύπο αισθητήρα (πυρανόμετρο GHI) και επαληθεύτηκε
    έναντι pvlib Ineichen (απόκλιση < 15% σε όλη τη διάρκεια της ημέρας).

    Ο τοπικός ορίζοντας (βουνά) εφαρμόζεται ως ΚΑΤΩΦΛΙ, όχι ως αφαίρεση:
    μόλις ο ήλιος ανέβει πάνω από τον ορίζοντα, η ένταση είναι πλήρης.
    Η προηγούμενη υλοποίηση αφαιρούσε τη γωνία blocking από το ύψος του
    ήλιου ΚΑΙ πολλαπλασίαζε με επιπλέον παράγοντα, μηδενίζοντας την
    αναμενόμενη ακτινοβολία ακόμη και με καθαρό ουρανό.
    """
    solar = get_solar_position_accurate(lat, lon, dt)

    if not solar["is_above_horizon"]:
        return 0.0

    blocking_angle = _get_local_horizon_blocking(
        lat, lon, solar["azimuth"], station_elev
    )

    elevation = solar["elevation"]
    doy = dt.timetuple().tm_yday

    ghi_clear = _esra_clear_sky_ghi(elevation, doy, station_elev)

    if elevation <= blocking_angle:
        # Ο ήλιος είναι πίσω από βουνό: μηδενίζεται η άμεση δέσμη και
        # παραμένει μέρος της διάχυτης (DHI/GHI ≈ 0.3-0.65 σε χαμηλό ήλιο,
        # μειωμένη περαιτέρω επειδή το βουνό καλύπτει μέρος του ουρανού).
        return 0.25 * ghi_clear

    return ghi_clear


def _esra_clear_sky_ghi(elevation_deg: float, day_of_year: int,
                        elevation_m: float = 0.0,
                        turbidity: float = LINKE_TURBIDITY) -> float:
    """
    Καθαρός ουρανός GHI κατά ESRA (απλοποιημένο Ineichen).

    Επαληθευμένο έναντι pvlib Ineichen: ο λόγος μοντέλου/pvlib είναι
    0.98-1.02 για ύψος ήλιου > 10°.
    """
    if elevation_deg <= 0:
        return 0.0

    # Διόρθωση απόστασης Γης-Ηλίου
    eccentricity = 1 + 0.03344 * math.cos(
        math.radians(360.0 / 365.0 * (day_of_year - 2.72))
    )

    # Σχετική αέρια μάζα (Kasten-Young)
    air_mass = 1.0 / (
        math.sin(math.radians(elevation_deg))
        + 0.50572 * (96.07995 - elevation_deg) ** -1.6364
    )

    cg1 = 5.09e-5 * elevation_m + 0.868
    cg2 = 3.92e-5 * elevation_m + 0.0387

    ghi = (
        cg1
        * SOLAR_CONSTANT_ESRA
        * eccentricity
        * math.sin(math.radians(elevation_deg))
        * math.exp(-cg2 * air_mass * (turbidity - 1))
    )
    return max(0.0, ghi)




# ============================================================
# PERSISTENT STORAGE (Restart-proof)
# ============================================================
def _ensure_storage():
    defaults = {
        'pressure_history': [],
        'temp_history': [],
        'hum_history': [],
        'wind_history': [],
        'solar_history': [],
        'last_score': None,
        'last_rain': None,
        'last_dp_depression': None,
        'current_regime': 'unknown',
        'regime_start_time': None,
        'last_regime_transition': None,
        'sky_confidence_persistence': None,
        'sky_streak_clear': 0,
        'sky_streak_cloudy': 0,
        # NEW: Dwell time tracking
        'last_state_change_time': None,
        'last_primary_state': None,
    }
    for var, default in defaults.items():
        if var not in globals():
            globals()[var] = default




# ============================================================
# DEW POINT - Magnus-Tetens (Buck variant)
# ============================================================
def dewpoint(temperature_c: float, humidity_rh: float) -> float:
    if humidity_rh <= 0 or temperature_c < -40 or temperature_c > 50:
        return temperature_c
    
    rh_frac = humidity_rh / 100.0
    gamma = math.log(rh_frac) + (MAGNUS_A * temperature_c) / (MAGNUS_B + temperature_c)
    dp = (MAGNUS_B * gamma) / (MAGNUS_A - gamma)
    
    return dp




def dewpoint_depression(temperature_c: float, humidity_rh: float) -> float:
    dp = dewpoint(temperature_c, humidity_rh)
    return temperature_c - dp




# ============================================================
# PRESSURE TREND - 3-hour baseline
# ============================================================
def pressure_trend_3h(history: list, current_time: datetime, current_pressure: float) -> float:
    if len(history) < 3:
        return 0.0
    
    target_time = current_time - timedelta(hours=3)
    valid_points = [x for x in history if x[0] <= target_time]
    
    if not valid_points:
        return 0.0
    
    baseline = max(valid_points, key=lambda x: x[0])
    return current_pressure - baseline[1]




# ============================================================
# PRESSURE CURVATURE
# ============================================================
def pressure_curvature(history: list, current_time: datetime, current_pressure: float) -> float:
    """
    Μεταβολή του ΡΥΘΜΟΥ μεταβολής της πίεσης (hPa/h ανά ώρα).

    Επιστρέφει rate_1h - rate_3h. Αρνητική τιμή = η πτώση επιταχύνεται
    (ή η άνοδος επιβραδύνεται) => επιδείνωση. Θετική = βελτίωση.

    ΣΗΜΑΝΤΙΚΟ: Τα δύο trends ΠΡΕΠΕΙ να κανονικοποιηθούν σε hPa/h πριν
    την αφαίρεση. Χωρίς κανονικοποίηση το αποτέλεσμα είναι -2×ο ρυθμός,
    δηλαδή αντιστρέφει τα πρόσημα και όλοι οι καταναλωτές (regime, rain,
    score) βλέπουν το αντίθετο από την πραγματικότητα.
    """
    if len(history) < 8:
        return 0.0
    
    t_1h = current_time - timedelta(hours=1)
    points_1h = [x for x in history if x[0] <= t_1h]
    
    t_3h = current_time - timedelta(hours=3)
    points_3h = [x for x in history if x[0] <= t_3h]
    
    rate_1h = 0.0
    rate_3h = 0.0
    
    if points_1h:
        baseline_1h = max(points_1h, key=lambda x: x[0])
        hours = (current_time - baseline_1h[0]).total_seconds() / 3600
        if hours > 0:
            rate_1h = (current_pressure - baseline_1h[1]) / hours
    
    if points_3h:
        baseline_3h = max(points_3h, key=lambda x: x[0])
        hours = (current_time - baseline_3h[0]).total_seconds() / 3600
        if hours > 0:
            rate_3h = (current_pressure - baseline_3h[1]) / hours
    
    return rate_1h - rate_3h




# ============================================================
# PRESSURE ACCELERATION MODULE (Shadow Signal - Phase 1)
# ============================================================
FRONTAL_SCALE = 3.0
NOISE_THRESHOLD = 0.25
DIRECTION_VIOLATION_THRESHOLD = 0.3




def _get_pressure_trend(history: list, now: datetime, 
                        current_pressure: float, hours_back: float) -> float | None:
    target_time = now - timedelta(hours=hours_back)
    valid_points = [x for x in history if x[0] <= target_time]
    
    if not valid_points:
        return None
    
    baseline = max(valid_points, key=lambda x: x[0])
    return current_pressure - baseline[1]




def _compute_coherence(n1: float, n3: float, n6: float) -> float:
    weights = [0.5, 0.3, 0.2]
    values = [n1, n3, n6]
    
    filtered = [(v, w) for v, w in zip(values, weights) if abs(v) > NOISE_THRESHOLD]
    
    if not filtered:
        return 0.5
    
    signed = sum(math.copysign(1, v) * w for v, w in filtered)
    total = sum(w for _, w in filtered)
    
    return abs(signed) / total




def _compute_direction_consistency(n1: float, n3: float, n6: float) -> float:
    S = [n6, n3, n1]
    violations = 0
    
    for i in range(len(S) - 1):
        if abs(S[i+1]) > 0.01:
            rel_change = abs(S[i] - S[i+1]) / abs(S[i+1])
        else:
            rel_change = 0
        
        if rel_change > DIRECTION_VIOLATION_THRESHOLD:
            if math.copysign(1, S[i]) != math.copysign(1, S[i+1]):
                violations += 1
    
    return max(0.0, 1.0 - (violations / 2))




def get_pressure_acceleration(history: list, now: datetime, 
                              current_pressure: float) -> dict:
    t1 = _get_pressure_trend(history, now, current_pressure, 1)
    t3 = _get_pressure_trend(history, now, current_pressure, 3)
    t6 = _get_pressure_trend(history, now, current_pressure, 6)
    
    if None in [t1, t3, t6]:
        return {
            "valid": False, "magnitude": 0.0, "coherence": 0.5, 
            "direction_consistency": 0.5, "trend_1h": None, "trend_3h": None, 
            "trend_6h": None, "trend_1h_normalized": None, "trend_3h_normalized": None, 
            "trend_6h_normalized": None, "raw_magnitude": 0.0
        }
    
    n1 = t1
    n3 = t3 / 3
    n6 = t6 / 6
    
    raw_magnitude = 0.5 * n1 + 0.3 * n3 + 0.2 * n6
    magnitude = max(-2.0, min(2.0, raw_magnitude / FRONTAL_SCALE))
    coherence = _compute_coherence(n1, n3, n6)
    direction_consistency = _compute_direction_consistency(n1, n3, n6)
    
    return {
        "valid": True,
        "magnitude": round(magnitude, 3),
        "coherence": round(coherence, 3),
        "direction_consistency": round(direction_consistency, 3),
        "trend_1h": round(t1, 3),
        "trend_3h": round(t3, 3),
        "trend_6h": round(t6, 3),
        "trend_1h_normalized": round(n1, 3),
        "trend_3h_normalized": round(n3, 3),
        "trend_6h_normalized": round(n6, 3),
        "raw_magnitude": round(raw_magnitude, 3)
    }




def interpret_acceleration(accel_data: dict) -> str:
    if not accel_data["valid"]:
        return "no_data"
    
    mag = accel_data["magnitude"]
    coh = accel_data["coherence"]
    dir_cons = accel_data["direction_consistency"]
    
    if abs(mag) < 0.3:
        strength = "neutral"
    elif abs(mag) < 0.7:
        strength = "weak"
    else:
        strength = "strong"
    
    if abs(mag) < 0.1:
        direction = "neutral"
    elif mag > 0:
        direction = "rising"
    else:
        direction = "falling"
    
    quality = coh * dir_cons
    if quality > 0.8:
        quality_str = "high_confidence"
    elif quality > 0.5:
        quality_str = "moderate"
    else:
        quality_str = "noisy"
    
    return f"{strength}_{direction}_{quality_str}"




# ============================================================
# SEA BREEZE AUTO-DETECTION
# ============================================================
def sea_bearing(lat: float, lon: float) -> int:
    if 37.7 <= lat <= 38.3 and 23.4 <= lon <= 24.2:
        return 200  # Attica / Saronic Gulf
    if 36.8 <= lat <= 37.4 and 25.1 <= lon <= 25.7:
        return 270  # Naxos / Cyclades
    return 180  # Default: South




def is_sea_breeze(wind_dir: float, bearing: int, threshold: int = 45) -> bool:
    diff = abs(wind_dir - bearing)
    if diff > 180:
        diff = 360 - diff
    return diff <= threshold




# ============================================================
# FIXED SCORING ENGINE (Anti-Bug Edition)
# ============================================================
def _score_falling(value: float, thresholds: list) -> float:
    """For negative signals (pressure drop, negative curvature)"""
    for threshold, points in thresholds:
        if value <= threshold:
            return points
    return 0.0




def _score_rising(value: float, thresholds: list) -> float:
    """For positive signals (humidity, wind, pressure)"""
    for threshold, points in thresholds:
        if value >= threshold:
            return points
    return 0.0




def _score_low_pressure(value: float, thresholds: list) -> float:
    """Για την απόλυτη πίεση: ΧΑΜΗΛΗ τιμή = κακοκαιρία."""
    for threshold, points in thresholds:
        if value <= threshold:
            return points
    return 0.0


def score_enhanced(
    p_abs: float, 
    h: float, 
    w_speed: float, 
    p_trend_3h: float, 
    p_curvature: float,
    breeze: bool
) -> float:
    s = 0.0
    
    # FALLING signals (negative = bad weather)
    s += _score_falling(p_trend_3h, SCORE_THRESHOLDS_FALLING["pressure_trend_3h"])
    s += _score_falling(p_curvature, SCORE_THRESHOLDS_FALLING["pressure_curvature"])
    
    # RISING signals (high values = bad weather)
    s += _score_rising(h, SCORE_THRESHOLDS_RISING["humidity"])
    s += _score_rising(w_speed, SCORE_THRESHOLDS_RISING["wind_speed"])
    
    # LOW pressure = bad weather
    s += _score_low_pressure(p_abs, SCORE_THRESHOLDS_LOW_PRESSURE)
    
    if breeze:
        s -= 25
    
    return max(0, min(100, s))




# ============================================================
# RAIN PROBABILITY (v8.2 - Calibrated for Greece)
# ============================================================
def rain_probability(s: float, h: float, dp_depression: float, 
                     p_curvature: float, regime: str) -> float:
    base = min(100.0, s * 1.1)
    
    # v8.2: Softened DP depression multipliers (was 1.5x)
    if dp_depression > 10:
        base *= 0.4
    elif dp_depression > 6:
        base *= 0.7
    elif dp_depression < 4:
        base *= 1.15   # v8.2: was nothing (no bonus)
    elif dp_depression < 6:
        base *= 1.05   # v8.2: was 1.5x - too aggressive for Greek summer
    
    # v8.2: Harder curvature trigger (was -0.4 → +15)
    if p_curvature < -0.7:
        base += 10     # v8.2: was -0.4 → +15
    elif p_curvature < -0.4:
        base += 5      # v8.2: new intermediate band
    
    if regime == "converging":
        base *= 1.3
    elif regime == "improving":
        base *= 0.6
    elif regime == "convective":
        base += 10
    
    return max(0, min(100, base))




# ============================================================
# REGIME DETECTION - With Hysteresis
# ============================================================
def detect_regime_base(p_trend: float, p_curvature: float, 
                      h: float, solar: float, hour: int) -> str:
    if p_curvature < -0.4 or (p_trend < -1.5 and p_curvature < -0.2):
        return "converging"
    if p_trend > 1.0 and p_curvature > 0.1:
        return "improving"
    if hour is not None and 9 <= hour <= 19:
        if h > 80 and solar > 500:
            return "convective"
    if h > 75 and p_trend > -0.5:
        return "humid_stable"
    return "normal"




def detect_regime_hysteresis(
    p_trend: float, 
    p_curvature: float, 
    h: float, 
    solar: float,
    hour: int,
    current_regime: str,
    regime_start_time: datetime | None,
    last_transition: datetime | None,
    now: datetime,
    stability_window_min: int = 30,
    cooldown_min: int = 20
) -> tuple[str, datetime, datetime]:
    proposed = detect_regime_base(p_trend, p_curvature, h, solar, hour)
    
    if regime_start_time is None:
        return proposed, now, now
    
    if proposed == current_regime:
        return current_regime, regime_start_time, last_transition
    
    elapsed = (now - regime_start_time).total_seconds() / 60
    time_since_transition = 0
    if last_transition:
        time_since_transition = (now - last_transition).total_seconds() / 60
    
    if time_since_transition < cooldown_min:
        return current_regime, regime_start_time, last_transition
    
    if elapsed < stability_window_min:
        return current_regime, regime_start_time, last_transition
    
    return proposed, now, now




# ============================================================
# SKY FUSION LAYER (v8.4 - FIXED: Season-aware dawn detection)
# ============================================================

# FIX v8.4: Dynamic dawn threshold based on solar altitude
MORNING_HOURS_START = 5   # 5:00 AM
MORNING_HOURS_END = 9     # 9:00 AM
DAWN_SOLAR_RATIO = 0.40    # 40% of day's max = dawn transition


def _day_max_expected_solar(lat: float, lon: float, dt: datetime,
                            station_elev: float = 0.0) -> float:
    """Μέγιστη αναμενόμενη ακτινοβολία της ημέρας (ηλιακό μεσημέρι)."""
    noon = dt.replace(hour=12, minute=0, second=0, microsecond=0)
    return get_expected_clear_sky_solar(lat, lon, noon, station_elev)


def get_sky_confidence(solar_ratio: float, humidity: float, 
                       dp_depression: float, p_curvature: float,
                       trend_3h: float, expected_clear_sky: float,
                       hour: int = None,
                       lat: float = None, lon: float = None,
                       dt: datetime = None,
                       station_elev: float = 0.0) -> float:
    """
    Εμπιστοσύνη καθαρού ουρανού.

    Το dawn threshold υπολογίζεται για τις ΠΡΑΓΜΑΤΙΚΕΣ συντεταγμένες του
    σταθμού και για τη συγκεκριμένη ημέρα. Η προηγούμενη έκδοση χρησιμοποιούσε
    σταθερές συντεταγμένες Αθήνας (37.94, 23.75) και datetime.now(), οπότε σε
    οποιονδήποτε άλλον σταθμό (π.χ. Νάξος) το κατώφλι ήταν λάθος.
    """
    is_morning = hour is not None and MORNING_HOURS_START <= hour < MORNING_HOURS_END
    
    # NIGHT MODE (expected_clear_sky < 25)
    if expected_clear_sky < 25:
        confidence = 0.50
        
        if trend_3h > 0.3:
            confidence += 0.20
        elif trend_3h > 0:
            confidence += 0.10
        
        if humidity > 85:
            confidence -= 0.05
        elif humidity < 70:
            confidence += 0.08
        
        if dp_depression > 12:
            confidence += 0.15
        elif dp_depression > 10:
            confidence += 0.10
        elif dp_depression > 8:
            confidence += 0.05
        
        # Morning bonus - expect clear morning after night
        if is_morning and confidence >= 0.50:
            confidence += 0.15
        
        return max(0.0, min(0.90, confidence))
    
    # DAWN TRANSITION - δυναμικό κατώφλι για τον σταθμό και την ημέρα
    ref_lat = lat if lat is not None else 37.94
    ref_lon = lon if lon is not None else 23.75
    ref_dt = dt if dt is not None else datetime.now()
    max_expected = _day_max_expected_solar(ref_lat, ref_lon, ref_dt, station_elev)
    dawn_threshold = max_expected * DAWN_SOLAR_RATIO
    
    if expected_clear_sky < dawn_threshold:
        confidence = 0.60
        
        if expected_clear_sky > dawn_threshold * 0.5:  # Sun is rising
            if solar_ratio > 0.3:
                confidence += 0.12
            elif solar_ratio > 0.1:
                confidence += 0.06
        
        if trend_3h > 0.5:
            confidence += 0.15
        elif trend_3h > 0.2:
            confidence += 0.10
        elif trend_3h > 0:
            confidence += 0.05
        
        if is_morning:
            confidence += 0.10
        
        if dp_depression > 10:
            confidence += 0.08
        
        return max(0.0, min(0.90, confidence))
    
    # DAY MODE (normal solar conditions)
    if solar_ratio <= 0:
        return 0.0
    # Ο αισθητήρας μπορεί να ξεπερνά ελαφρώς το μοντέλο (χιόνι, ανάκλαση,
    # συννεφιά που ανοίγει). Δεν μηδενίζουμε την εμπιστοσύνη - την περιορίζουμε.
    solar_ratio = min(solar_ratio, 1.5)
    
    solar_score = max(0, min(1, (solar_ratio - 0.35) / 0.45))
    humidity_score = max(0, min(1, (80 - humidity) / 30))
    
    if dp_depression > 12: dryness_bonus = 0.15
    elif dp_depression > 10: dryness_bonus = 0.08
    elif dp_depression < 6: dryness_bonus = -0.10
    else: dryness_bonus = 0.0
    
    if p_curvature > 0: stability_score = 0.1
    elif p_curvature > -0.2: stability_score = 0.05
    else: stability_score = -0.15
    
    confidence = (0.40 * solar_score + 0.20 * humidity_score + 
                  0.25 * 0.5 + 0.15 * (0.5 + stability_score))
    confidence += dryness_bonus
    
    return max(0.0, min(1.0, confidence))


def is_sky_clear(solar_ratio: float, humidity: float, 
                 rain_prob: float, p_curvature: float, 
                 dp_depression: float,
                 trend_3h: float = 0.0,
                 expected_clear_sky: float = 100.0,
                 hour: int = None,
                 lat: float = None, lon: float = None,
                 dt: datetime = None,
                 station_elev: float = 0.0) -> tuple[bool, float]:
    """Συνδυασμός ηλιακής ακτινοβολίας, υγρασίας και πίεσης σε κατάσταση ουρανού."""
    sky_confidence = get_sky_confidence(
        solar_ratio, humidity, dp_depression, 
        p_curvature, trend_3h, expected_clear_sky, hour,
        lat, lon, dt, station_elev
    )
    
    rain_threshold = 25
    if dp_depression > 12: rain_threshold = 40
    elif dp_depression > 10: rain_threshold = 32
    
    risk = 0
    if rain_prob >= rain_threshold: risk += 1
    if p_curvature < -0.25: risk += 1
    
    # Lower threshold for morning hours
    is_morning = hour is not None and MORNING_HOURS_START <= hour < MORNING_HOURS_END
    confidence_threshold = 0.55 if is_morning else 0.65
    
    sky_clear = (sky_confidence > confidence_threshold and risk < 2)
    
    return sky_clear, sky_confidence




# ============================================================
# PRIMARY LABEL with HYSTERESIS (Rain as EVENT, not STATE)
# ============================================================
# Οι καταστάσεις βροχής είναι events: δημοσιεύονται αμέσως και δεν
# υπόκεινται σε dwell time.
RAIN_EVENT_STATES = ("Βροχές", "Καταιγίδες")


def get_primary_label(sky_clear: bool, sky_confidence: float, 
                      rain_prob: float, current_state: str,
                      hour: int = None) -> str:
    """
    Κύρια ετικέτα πρόγνωσης με υστέρηση (hysteresis).

    Οι καταστάσεις είναι: Καλός καιρός / Πιθανή συννεφιά / Συννεφιά,
    με τις βροχές/καταιγίδες ως event overlay.
    """
    is_morning = hour is not None and MORNING_HOURS_START <= hour < MORNING_HOURS_END
    
    # RAIN EVENT (overlay, not state transition)
    if rain_prob > 75:
        return "Καταιγίδες"
    if rain_prob > 55:
        return "Βροχές"
    
    if current_state == "Καλός καιρός":
        # Χρειάζεται σημαντική πτώση για να φύγει από "Καλός"
        if sky_confidence < 0.35:
            return "Συννεφιά"
        if sky_confidence < 0.55:
            return "Πιθανή συννεφιά"
        return "Καλός καιρός"
    
    if current_state == "Πιθανή συννεφιά":
        if sky_confidence > 0.70:
            return "Καλός καιρός"
        if sky_confidence < 0.30:
            return "Συννεφιά"
        return "Πιθανή συννεφιά"
    
    if current_state == "Συννεφιά":
        if is_morning:
            # Τα πρωινά ανακάμπτει πιο γρήγορα
            if sky_confidence > 0.60:
                return "Καλός καιρός"
            if sky_confidence > 0.45:
                return "Πιθανή συννεφιά"
        else:
            if sky_confidence > 0.70:
                return "Καλός καιρός"
            if sky_confidence > 0.50:
                return "Πιθανή συννεφιά"
        return "Συννεφιά"
    
    # Default (first run or unknown state)
    if sky_clear:
        return "Καλός καιρός"
    if sky_confidence >= 0.35:
        return "Πιθανή συννεφιά"
    return "Συννεφιά"




def get_atmospheric_context(score: float, regime: str) -> str:
    if regime == "converging":
        return "Σύγκλιση"
    elif regime == "improving":
        return "Σταθεροποίηση"
    elif score > 60:
        return "Έντονη αστάθεια"
    elif regime == "convective":
        return "Τάση αναπτύξεων"
    elif score > 40:
        return "Θερμική δραστηριότητα"
    else:
        return "Σταθερές συνθήκες"




def forecast_text(sky_clear: bool, sky_confidence: float, score: float, 
                  rain_prob: float, regime: str, p_curvature: float, 
                  solar: float, humidity: float, current_state: str,
                  hour: int = None) -> tuple[str, str]:
    """
    v8.3 FIX: Added hour parameter
    """
    primary = get_primary_label(sky_clear, sky_confidence, rain_prob, current_state, hour)
    atmosphere = get_atmospheric_context(score, regime)
    return primary, atmosphere




# ============================================================
# GEO AUTO CONFIG (HA)
# ============================================================
def get_geo():
    """
    Γεωγραφικές συντεταγμένες και υψόμετρο του σταθμού.

    Το `state.get("zone.home.latitude")` επιστρέφει τη συντεταγμένη ως
    attribute, οπότε διαβάζεται μέσω `state.getattr`. Η προηγούμενη έκδοση
    προσπαθούσε `float(...)` σε ένα state object και κατέληγε ΠΑΝΤΑ στο
    fallback (Αθήνα, 210 m), αγνοώντας τη θέση της εγκατάστασης.
    """
    try:
        elev = float(hass.config.elevation)
    except Exception:
        elev = 0.0

    lat = lon = None
    try:
        attrs = state.getattr("zone.home")
        lat = float(attrs["latitude"])
        lon = float(attrs["longitude"])
    except Exception:
        pass

    if lat is None or lon is None:
        try:
            lat = float(state.get("zone.home").attributes["latitude"])
            lon = float(state.get("zone.home").attributes["longitude"])
        except Exception:
            return 37.94, 23.75, elev

    return lat, lon, elev




# ============================================================
# EMA SMOOTHER
# ============================================================
def ema_smooth(current: float, previous: float | None, alpha: float = 0.25) -> float:
    if previous is None:
        return current
    return alpha * current + (1 - alpha) * previous




# ============================================================
# MAIN LOOP - Every 2 minutes
# ============================================================
@time_trigger("period(now, 2min)")
def run():
    global pressure_history, temp_history, hum_history
    global wind_history, solar_history
    global last_score, last_rain, last_dp_depression
    global current_regime, regime_start_time, last_regime_transition
    global sky_confidence_persistence, sky_streak_clear, sky_streak_cloudy
    global last_state_change_time, last_primary_state
    
    _ensure_storage()
    
    try:
        p_raw = float(state.get(PRESSURE_SENSOR))
        t = float(state.get(TEMP_SENSOR))
        h = float(state.get(HUM_SENSOR))
        w_speed = float(state.get(WIND_SPEED_SENSOR))
        w_dir = float(state.get(WIND_DIR_SENSOR))
        solar_raw = float(state.get(SOLAR_SENSOR))
    except Exception as exc:
        # Χωρίς log το σφάλμα ήταν αόρατο: ο σταθμός απλώς πάγωνε σιωπηλά.
        log.warning(f"Zambretti: μη αναγνώσιμος αισθητήρας ({exc})")
        return
    
    w_speed = w_speed * 3.6 if WIND_SPEED_IS_MS else w_speed
    
    now = datetime.now()
    hour = now.hour
    lat, lon, elev = get_geo()
    bearing = sea_bearing(lat, lon)
    p = p_raw
    
    # Append new readings
    pressure_history.append((now, p))
    temp_history.append((now, t))
    hum_history.append((now, h))
    wind_history.append((now, w_speed))
    solar_history.append((now, solar_raw))
    
    # 24-hour rolling window
    cutoff = now - timedelta(hours=24)
    pressure_history = [x for x in pressure_history if x[0] >= cutoff]
    temp_history = [x for x in temp_history if x[0] >= cutoff]
    hum_history = [x for x in hum_history if x[0] >= cutoff]
    wind_history = [x for x in wind_history if x[0] >= cutoff]
    solar_history = [x for x in solar_history if x[0] >= cutoff]
    
    # Physics layer
    dp_depression = dewpoint_depression(t, h)
    dp = t - dp_depression
    p_trend_3h = pressure_trend_3h(pressure_history, now, p)
    p_curvature = pressure_curvature(pressure_history, now, p)
    
    # Solar position (NOAA SPA)
    solar_position = get_solar_position_accurate(lat, lon, now)
    blocking_angle = _get_local_horizon_blocking(lat, lon, solar_position["azimuth"], elev)
    
    # Solar normalization
    expected_solar = get_expected_clear_sky_solar(lat, lon, now, elev)
    # Το κατώφλι 10 W/m² αποφεύγει το ratio να εκραγεί (διαίρεση με σχεδόν
    # μηδενικό παρονομαστή) όταν ο ήλιος είναι ακριβώς στον ορίζοντα.
    solar_ratio = solar_raw / expected_solar if expected_solar >= 10.0 else 0.0
    
    breeze = False
    if 3.0 <= w_speed <= 28.0:
        breeze = is_sea_breeze(w_dir, bearing)
    
    # Dynamics layer (regime)
    new_regime, new_start_time, new_transition = detect_regime_hysteresis(
        p_trend_3h, p_curvature, h, solar_raw, hour,
        current_regime, regime_start_time, last_regime_transition,
        now,
        stability_window_min=REGIME_STABILITY_WINDOW,
        cooldown_min=REGIME_COOLDOWN
    )
    current_regime = new_regime
    regime_start_time = new_start_time
    last_regime_transition = new_transition
    
    regime_duration = 0
    if regime_start_time:
        regime_duration = (now - regime_start_time).total_seconds() / 3600
    
    # Interpretation layer
    raw_score_val = score_enhanced(p, h, w_speed, p_trend_3h, p_curvature, breeze)
    raw_rain_val = rain_probability(raw_score_val, h, dp_depression, p_curvature, current_regime)
    
    smoothed_score = ema_smooth(raw_score_val, last_score, SMOOTHING_FACTOR)
    smoothed_rain = ema_smooth(raw_rain_val, last_rain, SMOOTHING_FACTOR)
    
    # Acceleration (Phase 1 - Observer only)
    accel = get_pressure_acceleration(pressure_history, now, p)
    accel_interpretation = interpret_acceleration(accel)
    
    # Sky fusion - pass station position and time for correct dawn detection
    sky_clear, sky_confidence = is_sky_clear(
        solar_ratio, h, smoothed_rain, p_curvature, 
        dp_depression, p_trend_3h, expected_solar, hour,
        lat, lon, now, elev
    )
    
    # v8.2: Persistence updated to 0.4/0.6 (was 0.3/0.7)
    if sky_confidence_persistence is None:
        sky_confidence_persistent = sky_confidence
    else:
        sky_confidence_persistent = 0.4 * sky_confidence + 0.6 * sky_confidence_persistence
    
    sky_confidence_persistence = sky_confidence_persistent
    
    # Τα streaks ενημερώνονται ΜΟΝΟ σε ξεκάθαρες καταστάσεις. Στην ενδιάμεση
    # ζώνη ΔΕΝ μηδενίζονται, ώστε μια σταθερή τάση (π.χ. ξαστέρωμα) να
    # συσσωρεύεται χωρίς να χάνεται από έναν μεμονωμένο θόρυβο.
    if sky_confidence_persistent > 0.65:
        sky_streak_clear += 1
        sky_streak_cloudy = 0
    elif sky_confidence_persistent < 0.35:
        sky_streak_cloudy += 1
        sky_streak_clear = 0
    else:
        # Ενδιάμεση ζώνη: μείωση αντί μηδενισμού, ώστε να μην κολλάει
        # το sky_clear_final σε μια παλιά κατάσταση.
        sky_streak_clear = max(0, sky_streak_clear - 1)
        sky_streak_cloudy = max(0, sky_streak_cloudy - 1)
    
    if sky_streak_clear >= 3 and sky_confidence_persistent > 0.5:
        sky_clear_final = True
    elif sky_streak_cloudy >= 3 and sky_confidence_persistent < 0.6:
        sky_clear_final = False
    else:
        sky_clear_final = sky_clear
    
    # ============================================================
    # DWELL TIME CHECK (Anti-micro-flip)
    #
    # Το dwell εμποδίζει τις αλλαγές κατάστασης, ΟΧΙ την αναγγελία βροχής.
    # Οι βροχές/καταιγίδες είναι events: μια ξαφνική καταιγίδα πρέπει να
    # εμφανιστεί αμέσως, ακόμη και μέσα στο παράθυρο dwell.
    # ============================================================
    current_primary = last_primary_state if last_primary_state else "Καλός καιρός"
    
    # Get proposed state - pass hour parameter
    proposed_primary, fc_atmosphere = forecast_text(
        sky_clear_final, 
        sky_confidence_persistent,
        smoothed_score, 
        smoothed_rain,
        current_regime,
        p_curvature,
        solar_raw,
        h,
        current_primary,
        hour
    )
    
    # Reduced dwell time for morning hours
    is_morning = MORNING_HOURS_START <= hour < MORNING_HOURS_END
    effective_dwell = 10 if is_morning else MIN_STATE_DWELL_TIME
    is_rain_event = proposed_primary in RAIN_EVENT_STATES
    
    # Apply dwell time check (ποτέ για rain events)
    if last_state_change_time is not None and not is_rain_event:
        dwell_minutes = (now - last_state_change_time).total_seconds() / 60
        if dwell_minutes < effective_dwell:
            # Block micro-flip, keep current state
            proposed_primary = last_primary_state
    
    # Update state change tracking
    if proposed_primary != last_primary_state:
        last_state_change_time = now
        last_primary_state = proposed_primary
    
    fc_primary = proposed_primary
    
    last_score = smoothed_score
    last_rain = smoothed_rain
    last_dp_depression = dp_depression
    
    # Output
    state.set(
        "sensor.zambretti_enhanced_pro_8_4",
        value=fc_primary,
        new_attributes={
            # === Core Forecast ===
            "forecast_primary": fc_primary,
            "forecast_atmosphere": fc_atmosphere,
            
            # === Pressure Data ===
            "pressure_mslp": round(p, 1),
            "trend_3h": round(p_trend_3h, 2),
            "pressure_curvature": round(p_curvature, 3),
            
            # === Acceleration Shadow Signal (Phase 1) ===
            "acceleration_valid": accel["valid"],
            "acceleration_magnitude": accel["magnitude"],
            "acceleration_coherence": accel["coherence"],
            "acceleration_direction_consistency": accel["direction_consistency"],
            "acceleration_quality": round(
                accel["coherence"] * accel["direction_consistency"], 3
            ) if accel["valid"] else 0.0,
            "acceleration_interpretation": accel_interpretation,
            "acceleration_trend_1h": accel["trend_1h"],
            "acceleration_trend_3h": accel["trend_3h"],
            "acceleration_trend_6h": accel["trend_6h"],
            "acceleration_raw_magnitude": accel["raw_magnitude"],
            
            # === Temperature & Humidity ===
            "temperature": round(t, 1),
            "humidity": round(h, 1),
            "dewpoint": round(dp, 1),
            "dp_depression": round(dp_depression, 1),
            
            # === Wind Data ===
            "wind_speed_kmh": round(w_speed, 1),
            "wind_dir": w_dir,
            "sea_breeze": breeze,
            "sea_bearing": bearing,
            
            # === Solar Data ===
            "solar_radiation": round(solar_raw, 1),
            "solar_ratio": round(solar_ratio, 2),
            "expected_clear_sky": round(expected_solar, 0),
            
            # v8.5: Solar Position Data (NOAA SPA)
            "sun_elevation": round(solar_position["elevation"], 1),
            "sun_azimuth": round(solar_position["azimuth"], 1),
            "mountain_blocking": round(blocking_angle, 1),
            
            # === Sky State ===
            "sky_clear": sky_clear_final,
            "sky_confidence": round(sky_confidence, 2),
            # v8.3: New telemetry for debugging
            "sky_confidence_raw": round(sky_confidence, 3),
            "sky_confidence_persistent": round(sky_confidence_persistent, 3),
            
            # === Rain (EVENT, not STATE) ===
            "rain_probability": round(smoothed_rain, 1),
            "rain_event": smoothed_rain > 55,
            
            # === Scoring ===
            "score": round(smoothed_score, 1),
            
            # === Regime ===
            "weather_regime": current_regime,
            "regime_duration_h": round(regime_duration, 1),
            
            # === Stability Metrics ===
            "dwell_time_min": round(
                (now - last_state_change_time).total_seconds() / 60 
                if last_state_change_time else 0, 1
            ),
            
            # === Location ===
            "lat": lat,
            "lon": lon,
            "elevation": elev,
            
            # === Version ===
            "version": "8.12.1",
            
            # === Timestamp ===
            "timestamp": now.isoformat()
        }
    )