# 🌦️ Zambretti Enhanced Pro v8.12.1

**Προηγμένο σύστημα πρόβλεψης καιρού για Home Assistant με αισθητήρα Ecowitt GW2000A**

Βασισμένο στον αλγόριθμο Zambretti με πρόσθετα χαρακτηριστικά:
- Ανίχνευση θαλάσσιας αύρας (Αττική & Κυκλάδες)
- Υπολογισμός σημείου δρόσου
- Ανάλυση τάσης πίεσης (curvature, acceleration)
- Fusion αισθητήρα ηλιακής ακτινοβολίας
- Αυτόματη ανίχνευση καιρικού καθεστώτος (regime detection)
- **Επαληθευμένη βάση Ελληνικών βουνών** (54 κορυφές, SRTM 90m)
- **Βαθμονομημένο προφίλ ορίζοντα** (SRTM, σταθμός Γλινάδας Νάξου)

---

## 📋 Περιεχόμενα

- [Χαρακτηριστικά](#-χαρακτηριστικά)
- [Απαιτήσεις](#-απαιτήσεις)
- [Εγκατάσταση](#-εγκατάσταση)
- [Διαμόρφωση](#-διαμόρφωση)
- [Αισθητήρες Εξόδου](#-αισθητήρες-εξόδου)
- [Αλγόριθμος](#-αλγόριθμος)
- [Changelog](#-changelog)
- [Συνεισφορά](#-συνεισφορά)
- [Άδεια](#-άδεια)

---

## ✨ Χαρακτηριστικά

### 🌡️ Φυσικές Μετρήσεις
- **Σχετική Πίεση**: Χρήση πίεσης αισθητήρα (όχι MSLP) για ακρίβεια
- **Θερμοκρασία/Υγρασία**: Υπολογισμός σημείου δρόσου (Magnus-Tetens Buck 1981)
- **Ηλιακή Ακτινοβολία**: Κανονικοποίηση βάσει γεωγραφικού πλάτους/μήκους

### 📊 Ανάλυση Τάσεων
- **3-ωρη τάση πίεσης**: Βασικός δείκτης μεταβολής καιρού
- **Πίεση Curvature**: Ανίχνευση επιτάχυνσης/επιβράδυνσης
- **Pressure Acceleration (Phase 1)**: Σκιώδες σήμα για μελλοντική χρήση

### 🌊 Θαλάσσια Αύρα
- Αυτόματη ανίχνευση για Αττική και Κυκλάδες
- Προσαρμοσμένη κατεύθυνση ανέμου ανά περιοχή

### 🎯 Ανίχνευση Καθεστώτος
- **Converging**: Σύγκλιση αέριων μαζών → πιθανές βροχές
- **Improving**: Βελτίωση καιρού
- **Convective**: Θερμική αστάθεια (9:00-19:00)
- **Humid Stable**: Υγρές σταθερές συνθήκες
- **Normal**: Κανονικές συνθήκες

### ☀️ Ηλιακός Υπολογισμός (v8.7)
- **NOAA Solar Position Algorithm**: Ακριβής υπολογισμός θέσης ήλιου
- **SRTM-Style Horizon Profile**: Πλήρες προφίλ ορίζοντα βάσει θέσης ήλιου
- **Αυτόματος υπολογισμός αποκλεισμού**: Μόνο όταν ο ήλιος είναι πίσω από βουνό
- **Ελληνική Βάση Βουνών**: 10+ βουνά σε όλη την Ελλάδα
- **Δυναμικό κατώφλι αυγής**: 40% της μέγιστης ηλιακής ακτινοβολίας

### 🔄 Hysteresis & Anti-Micro-Flip
- Ελάχιστος χρόνος παραμονής κατάστασης (25 λεπτά)
- Cooldown μεταξύ αλλαγών κατάστασης
- Αντιστροφή ορίων για αποφυγή ταλάντωσης

---

## 📋 Απαιτήσεις

### Υλικό
- **Home Assistant** (2024.1 ή νεότερο)
- **Ecowitt GW2000A** (ή συμβατός αισθητήρας)
- **WiFi Gateway** (π.χ. GW1000, WH2650)

### Home Assistant Configuration
```yaml
# configuration.yaml
homeassistant:
  packages:
    zambretti: !include zambretti_enhanced_pro_8_3.yaml
```

---

## 🔧 Εγκατάσταση

### Βήμα 1: Αντιγραφή Αρχείου
Αντιγράψτε το `zambretti_enhanced_pro_8_3.yaml` στον φάκελο `config/packages/`

### Βήμα 2: Διαμόρφωση Αισθητήρων
Ενημερώστε τα entity IDs στο αρχείο αν χρειάζεται:
```yaml
sensor:
  - platform: template
    sensors:
      zambretti_enhanced_pro_8_2:
        value_template: "{{ states('sensor.zambretti_enhanced_pro_8_2') }}"
        attribute_templates:
          # ... τα attributes
```

### Βήμα 3: Επανεκκίνηση
```bash
ha core restart
```

---

## ⚙️ Διαμόρφωση

### Αισθητήρες Εισόδου
```python
PRESSURE_SENSOR = "sensor.gw2000a_relative_pressure"
TEMP_SENSOR = "sensor.gw2000a_outdoor_temperature"
HUM_SENSOR = "sensor.gw2000a_humidity"
WIND_SPEED_SENSOR = "sensor.gw2000a_wind_speed"
WIND_DIR_SENSOR = "sensor.gw2000a_wind_direction"
SOLAR_SENSOR = "sensor.gw2000a_solar_radiation"
```

### Παράμετροι Λογικής
```python
# Ώρες πρωινού (για morning boost)
MORNING_HOURS_START = 5   # 5:00 π.μ.
MORNING_HOURS_END = 9     # 9:00 π.μ.

# Όριο αυγής (W/m²)
DAWN_UPPER_LIMIT = 400

# Χρόνοι σταθερότητας
REGIME_STABILITY_WINDOW = 30  # λεπτά
REGIME_COOLDOWN = 20          # λεπτά
MIN_STATE_DWELL_TIME = 25      # λεπτά

# Hysteresis
STATE_UPPER_HYSTERESIS = 48
STATE_LOWER_HYSTERESIS = 38

# Smoothing
SMOOTHING_FACTOR = 0.25
```

---

## 📊 Αισθητήρες Εξόδου

### Κύριος Αισθητήρας
```
sensor.zambretti_enhanced_pro_8_4
```

### v8.7 Νέα Attributes

| Attribute | Περιγραφή | Μονάδα |
|-----------|-----------|--------|
| `sun_elevation` | Ύψος ήλιου (°) | ° |
| `sun_azimuth` | Αζιμούθιο ήλιου (°) | ° |
| `mountain_blocking` | Αποκλεισμός βουνών | ° |
| `expected_clear_sky` | Αναμενόμενη ακτινοβολία | W/m² |

### Πλήρης Λίστα Attributes

| Attribute | Περιγραφή | Μονάδα |
|-----------|-----------|--------|
| `forecast_primary` | Κύρια πρόβλεψη | - |
| `forecast_atmosphere` | Ατμοσφαιρικές συνθήκες | - |
| `pressure_mslp` | Πίεση | hPa |
| `trend_3h` | Τάση 3 ωρών | hPa |
| `pressure_curvature` | Καμπυλότητα πίεσης | hPa/h |
| `temperature` | Θερμοκρασία | °C |
| `humidity` | Υγρασία | % |
| `dewpoint` | Σημείο δρόσου | °C |
| `dp_depression` | Κατάθλιψη δρόσου | °C |
| `wind_speed_kmh` | Ταχύτητα ανέμου | km/h |
| `wind_dir` | Διεύθυνση ανέμου | ° |
| `sea_breeze` | Ανίχνευση αύρας | true/false |
| `sea_bearing` | Κατεύθυνση αύρας | ° |
| `solar_radiation` | Ηλιακή ακτινοβολία | W/m² |
| `solar_ratio` | Λόγος ηλιακής/αναμενόμενης | - |
| `expected_clear_sky` | Αναμενόμενο clear sky | W/m² |
| `sun_elevation` | Ύψος ήλιου | ° |
| `sun_azimuth` | Αζιμούθιο ήλιου | ° |
| `mountain_blocking` | Αποκλεισμός βουνών | ° |
| `sky_clear` | Καθαρός ουρανός | true/false |
| `sky_confidence` | Εμπιστοσύνη ουρανού | 0-1 |
| `sky_confidence_raw` | Εμπιστοσύνη (raw) | 0-1 |
| `sky_confidence_persistent` | Εμπιστοσύνη (smoothed) | 0-1 |
| `rain_probability` | Πιθανότητα βροχής | % |
| `rain_event` | Ενεργό βροχής event | true/false |
| `score` | Σκορ καιρού | 0-100 |
| `weather_regime` | Καθεστώς καιρού | - |
| `regime_duration_h` | Διάρκεια καθεστώτος | h |
| `dwell_time_min` | Χρόνος παραμονής | min |
| `acceleration_interpretation` | Ερμηνεία επιτάχυνσης | - |
| `acceleration_magnitude` | Μέγεθος επιτάχυνσης | - |
| `acceleration_quality` | Ποιότητα επιτάχυνσης | 0-1 |
| `lat` | Γεωγραφικό πλάτος | ° |
| `lon` | Γεωγραφικό μήκος | ° |
| `elevation` | Υψόμετρο | m |
| `version` | Έκδοση κώδικα | - |
| `timestamp` | Χρονοσημαντήρα | ISO |

---

## 🧮 Αλγόριθμος

### Ροή Επεξεργασίας

```
┌─────────────┐
│   Sensors   │
└──────┬──────┘
       ▼
┌─────────────┐
│  Physics    │ ← Dewpoint, Pressure Trend, Curvature
└──────┬──────┘
       ▼
┌─────────────┐
│  Dynamics   │ ← Regime Detection with Hysteresis
└──────┬──────┘
       ▼
┌─────────────┐
│Interpretation│ ← Scoring, Rain Probability
└──────┬──────┘
       ▼
┌─────────────┐
│ Sky Fusion  │ ← Solar + Humidity + Pressure
└──────┬──────┘
       ▼
┌─────────────┐
│  Primary    │ ← Hysteresis + Dwell Time
│   Label     │
└─────────────┘
```

### Τύποι

**Σημείο Δρόσου (Magnus-Tetens)**
```
γ = ln(RH/100) + (A·T) / (B + T)
Td = (B·γ) / (A - γ)
```

**Τάση Πίεσης 3-ωρη**
```
ΔP = P_current - P_3h_ago
```

**Πιθανότητα Βροχής**
```
P_rain = min(100, score × 1.1 × modifiers)
```

---

## 📱 Lovelace Dashboard

Δες το αρχείο `lovelace_dashboard.yaml` για πλήρη κάρτα Home Assistant.

### Χρήση:
1. Αντέγραψε το περιεχόμενο του `lovelace_dashboard.yaml`
2. Πήγαινε στο Home Assistant → Overview → Edit Dashboard
3. Add Card → Manual Card → Paste the YAML

---

## 📝 Changelog

### v8.12.1 (2026-09-17)
#### Διορθώσεις ακρίβειας πρόγνωσης
- **Θέση ήλιου**: Αντικαταστάθηκε η απλοποιημένη μέθοδος με NOAA SPA. Το σφάλμα
  στο ύψος του ήλιου έπεσε από **12.96° σε 0.27°**, στο αζιμούθιο σε **0.01°**.
- **Ζώνη ώρας**: Ο υπολογισμός UTC χρησιμοποιεί πλέον τη ζώνη της εγκατάστασης
  (`hass.config.time_zone`) με σωστή θερινή ώρα, αντί για σταθερό +3.
- **Καθαρός ουρανός**: Νέο μοντέλο ESRA/Ineichen με `LINKE_TURBIDITY = 5.0`.
  Ο λόγος μοντέλου/pvlib είναι 0.87–1.30 (μέσος 1.04).
- **Ορίζοντας**: Το προφίλ αποκλεισμού μετριέται από SRTM 90m αντί για
  χειροκίνητη λίστα. Η γωνία έπεσε από **16–17° σε 0–5.4°**. Προστέθηκε
  εναλλαγή σε γενική βάση βουνών εκτός της βαθμονομημένης περιοχής.
- **Βάση βουνών**: Ξαναχτίστηκε από SRTM 90m — 54 κορυφές με επαληθευμένα
  υψόμετρα (η παλιά λίστα είχε σφάλματα έως 2370 m).
- **Καμπυλότητα πίεσης**: Τα trends κανονικοποιούνται σε hPa/h πριν την
  αφαίρεση. Πριν το αποτέλεσμα ήταν -2×ο ρυθμός και αντέστρεφε τα πρόσημα.
- **Scoring πίεσης**: Η απόλυτη πίεση βαθμολογείται πλέον με κατιούσα κλίμακα
  (χαμηλή = κακοκαιρία). Πριν έδινε 15 πόντους σε πίεση 1000+ hPa.
- **Σημείο δρόσου**: Συντελεστές Buck (1981) για νερό (17.502 / 240.97).
- **Βροχή**: Οι καταστάσεις βροχής είναι events και δεν μπλοκάρονται από dwell.
- **Σιωπηλά σφάλματα**: Το `except:` στη ανάγνωση αισθητήρων έγινε
  `except Exception` με καταγραφή, ώστε να μην παγώνει αθόρυβα ο σταθμός.

#### Έλεγχος
- `python harness/test_forecast.py` — 28 έλεγχοι, όλοι περνούν.
- `python harness/scenarios.py` — σενάρια ημέρας για οπτικό έλεγχο.
- `python harness/build_horizon_profile.py` — αναπαραγωγή προφίλ SRTM.

### v8.12 (2026-06-16)
#### Λόφοι Γλινάδα Νάξου
- **Νέοι λόφοι**: Προστέθηκαν τοπικοί λόφοι γύρω από τον σταθμό Γλινάδα Νάξου (37.073583, 25.398755)
- **Blocking**: Ανατολικός λόφος (127μ) → 15.9° το πρωί
- **Blocking**: Νότιος λόφος (119μ) → 3.4° το πρωί
- **SRTM elevations**: Διορθωμένα υψόμετρα για την περιοχή Νάξου

### v8.11 (2026-06-16)
#### Βουνά Νάξου & Κυκλάδων
- **Νάξος**: Ζαγορά (999μ), Μουτζούρης (905μ), Λιβάδια (650μ), Βίγλα (420μ)
- **Κοντινά νησιά**: Άνδρος, Πάρος, Αντίπαρος, Δονούσα, Ηρακλειά
- **Sea breeze**: Διορθωμένη κατεύθυνση για Κυκλάδες (270°)

### v8.10 (2026-06-16)
#### Πλήρης βάση Ελληνικών βουνών
- **70+ βουνά** σε όλη την Ελλάδα
- Αυτόματος υπολογισμός αποκλεισμού βάσει απόστασης
- Περιλαμβάνει: Αττική, Θεσσαλονίκη, Πάτρα, Λάρισα, Ιωάννινα, Βόλο, Κρήτη, νησιά

### v8.9 (2026-06-15)
#### Διόρθωση Υμηττού
- **Spread angle**: Αυξήθηκε σε 35° για πρωινές ώρες
- **Συντεταγμένες**: Διορθωμένες (37.938, 23.84)

### v8.8 (2026-06-15)
#### Διόρθωση ηλιακής θέσης
- **Timezone**: Προστέθηκε υποστήριξη για Greece (UTC+3)
- **Solar noon**: Διορθώθηκε βάσει longitude

---

## 🤝 Συνεισφορά

1. Fork το repository
2. Δημιουργία feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit αλλαγών (`git commit -m 'Add AmazingFeature'`)
4. Push στο branch (`git push origin feature/AmazingFeature`)
5. Άνοιγμα Pull Request

---

## 📄 Άδεια

Διανέμεται υπό την MIT License. Δείτε το αρχείο `LICENSE` για λεπτομέρειες.

---

## 👤 Συγγραφέας

**Iakovosv** - [GitHub Profile](https://github.com/Iakovosv)

---

## 🙏 Ευχαριστίες

- Βασισμένο στον αλγόριθμο [Zambretti](https://en.wikipedia.org/wiki/Zambretti_forecaster)
- Magnus-Tetens formula (Buck 1981)
- Κοινότητα Home Assistant για την υποστήριξη

---

⭐ Αν σας φάνηκε χρήσιμο, αφήστε ένα αστέρι στο repo!