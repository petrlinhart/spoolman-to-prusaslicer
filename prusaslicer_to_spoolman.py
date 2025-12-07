import configparser
import requests
import os

SPOOLMAN_URL = "http://homeassistant.local:7912/api/v1"
EXPORT_FILE = "PrusaSlicer_config_bundle.ini"

DEBUG = True

# ==============================
# Pomocné funkce
# ==============================

def safe_float(value, name, section):
    try:
        return float(value)
    except:
        print(f"⚠️ NEMAPOVATELNÉ ČÍSLO: [{section}] {name} = {value}")
        return None


def log(msg):
    print(msg)


# ==============================
# Načtení exportu
# ==============================

if not os.path.exists(EXPORT_FILE):
    print(f"❌ Soubor nenalezen: {EXPORT_FILE}")
    raise SystemExit(1)

config = configparser.ConfigParser()
config.read(EXPORT_FILE, encoding="utf-8")

# ==============================
# Načtení existujících vendorů
# ==============================

vendors = {}
r = requests.get(f"{SPOOLMAN_URL}/vendor")
for v in r.json():
    vendors[v["name"].lower()] = v["id"]

# ==============================
# Načtení existujících filamentů
# ==============================

filaments = {}
r = requests.get(f"{SPOOLMAN_URL}/filament")
for f in r.json():
    filaments[f["name"].lower()] = f["id"]

# ==============================
# Zpracování filamentů
# ==============================

for section in config.sections():

    if not section.startswith("filament:"):
        continue

    name = section.replace("filament:", "").strip()
    data = config[section]

    log(f"\n➡️ Filament: {name}")

    # ==============================
    # Povinná pole
    # ==============================

    required = [
        "filament_type",
        "filament_density",
        "filament_diameter",
        "temperature",
        "bed_temperature",
        "filament_vendor"
    ]

    missing = [k for k in required if k not in data]

    if missing:
        log(f"❌ CHYBÍ POVINNÁ POLE: {missing}")
        continue

    material = data["filament_type"]
    density = safe_float(data["filament_density"], "filament_density", section)
    diameter = safe_float(data["filament_diameter"], "filament_diameter", section)
    nozzle = safe_float(data["temperature"], "temperature", section)
    bed = safe_float(data["bed_temperature"], "bed_temperature", section)

    vendor_name = data["filament_vendor"].strip()

    color = data.get("filament_colour", "").replace("#", "")
    cost_per_kg = safe_float(data.get("filament_cost", 0), "filament_cost", section)
    spool_weight = safe_float(data.get("filament_spool_weight", 0), "filament_spool_weight", section)

    max_vol = safe_float(data.get("filament_max_volumetric_speed", 0), "filament_max_volumetric_speed", section)

    # ==============================
    # Cena za gram
    # ==============================

    if cost_per_kg and cost_per_kg > 0:
        price_per_gram = cost_per_kg / 1000.0
    else:
        price_per_gram = 0

    # ==============================
    # Vendor – vytvoření
    # ==============================

    vendor_key = vendor_name.lower()

    if vendor_key not in vendors:
        log(f"➕ Vytvářím výrobce: {vendor_name}")

        r = requests.post(
            f"{SPOOLMAN_URL}/vendor",
            json={"name": vendor_name}
        )

        if r.status_code != 200:
            log(f"❌ CHYBA VYTVÁŘENÍ VÝROBCE: {vendor_name}")
            continue

        vendor_id = r.json()["id"]
        vendors[vendor_key] = vendor_id

    else:
        vendor_id = vendors[vendor_key]

    # ==============================
    # Filament – vytvoření / update
    # ==============================

    filament_payload = {
        "name": name,
        "material": material,
        "density": density,
        "diameter": diameter,
        "price": cost_per_kg,
        "spool_weight": spool_weight,
        "settings_extruder_temp": nozzle,
        "settings_bed_temp": bed,
        "vendor_id": vendor_id,
        "color_hex": color,
        "extra": {
            "price_per_gram": price_per_gram,
            "max_volumetric_speed": max_vol
        }
    }

    filament_key = name.lower()

    if filament_key in filaments:
        filament_id = filaments[filament_key]
        r = requests.patch(
            f"{SPOOLMAN_URL}/filament/{filament_id}",
            json=filament_payload
        )

        if r.status_code == 200:
            log(f"🔄 Aktualizováno")
        else:
            log(f"❌ Chyba aktualizace")

    else:
        r = requests.post(
            f"{SPOOLMAN_URL}/filament",
            json=filament_payload
        )

        if r.status_code == 200:
            filaments[filament_key] = r.json()["id"]
            log(f"✅ Vytvořen nový filament")
        else:
            log(f"❌ Chyba vytvoření")

# ==============================
# Hotovo
# ==============================

print("\n🔥 IMPORT DOKONČEN")
