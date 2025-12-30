import configparser
import requests
import os

SPOOLMAN_URL = "http://homeassistant.local:7912/api/v1"
EXPORT_FILE = "PrusaSlicer_config_bundle.ini"

# ==============================
# Pomocné funkce
# ==============================

def log(msg):
    print(msg)

def safe_float(value, name, section):
    try:
        return float(value)
    except:
        log(f"⚠️ Nelze převést [{section}] {name} = {value}")
        return None

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
if r.status_code != 200:
    print("❌ Nelze načíst výrobce")
    raise SystemExit(1)

for v in r.json():
    vendors[v["name"].strip().lower()] = v["id"]

# ==============================
# Načtení existujících filamentů
# ==============================

filaments = {}
r = requests.get(f"{SPOOLMAN_URL}/filament")
if r.status_code != 200:
    print("❌ Nelze načíst filamenty")
    raise SystemExit(1)

for f in r.json():
    filaments[f["name"].strip().lower()] = f["id"]

# ==============================
# Zpracování USER filamentů
# ==============================

for section in config.sections():

    if not section.startswith("filament:"):
        continue

    name = section.replace("filament:", "").strip()
    data = config[section]

    # ==============================
    # ❌ IGNORACE SPOOLMAN FILAMENTŮ
    # ==============================

    if name.lower().startswith("spoolman_"):
        log(f"⏭ Přeskakuji Spoolman filament: {name}")
        continue

    # ==============================
    # POVINNÁ POLE
    # ==============================

    if "filament_vendor" not in data:
        log(f"⚠️ [{name}] chybí filament_vendor – přeskočeno")
        continue

    if "filament_type" not in data:
        log(f"⚠️ [{name}] chybí filament_type – přeskočeno")
        continue

    vendor_name = data["filament_vendor"].strip()
    if not vendor_name:
        log(f"⚠️ [{name}] prázdný výrobce – přeskočeno")
        continue

    material = data["filament_type"]

    density  = safe_float(data.get("filament_density"), "filament_density", name)
    diameter = safe_float(data.get("filament_diameter"), "filament_diameter", name)
    nozzle   = safe_float(data.get("temperature"), "temperature", name)
    bed      = safe_float(data.get("bed_temperature"), "bed_temperature", name)
    cost     = safe_float(data.get("filament_cost"), "filament_cost", name)
    spool_w  = safe_float(data.get("filament_spool_weight"), "filament_spool_weight", name)

    color = data.get("filament_colour", "").replace("#", "")

    log(f"\n➡️ Filament: {name}")
    log(f"   Výrobce: {vendor_name}")
    log(f"   Materiál: {material}")

    # ==============================
    # VÝROBCE – vytvoření pokud chybí
    # ==============================

    vkey = vendor_name.lower()

    if vkey not in vendors:
        log(f"➕ Vytvářím výrobce: {vendor_name}")

        r = requests.post(
            f"{SPOOLMAN_URL}/vendor",
            json={"name": vendor_name}
        )

        if r.status_code != 200:
            log(f"❌ Chyba vytvoření výrobce: {vendor_name}")
            log(r.text)
            continue

        vendors[vkey] = r.json()["id"]

    vendor_id = vendors[vkey]

    # ==============================
    # FILAMENT PAYLOAD
    # ==============================

    payload = {
        "name": name,
        "material": material,
        "vendor_id": vendor_id,
        "diameter": diameter,
        "density": density,
        "price": cost,
        "spool_weight": spool_w,
        "settings_extruder_temp": nozzle,
        "settings_bed_temp": bed,
        "color_hex": color
    }

    fkey = name.lower()

    # ==============================
    # CREATE / UPDATE
    # ==============================

    if fkey in filaments:
        filament_id = filaments[fkey]

        r = requests.patch(
            f"{SPOOLMAN_URL}/filament/{filament_id}",
            json=payload
        )

        if r.status_code == 200:
            log("🔄 Aktualizováno")
        else:
            log("❌ Chyba aktualizace")
            log(r.text)

    else:
        r = requests.post(
            f"{SPOOLMAN_URL}/filament",
            json=payload
        )

        if r.status_code == 200:
            filaments[fkey] = r.json()["id"]
            log("✅ Vytvořen nový filament")
        else:
            log("❌ Chyba vytvoření filamentu")
            log(r.text)

# ==============================
# Hotovo
# ==============================

print("\n🔥 IMPORT UŽIVATELSKÝCH FILAMENTŮ DOKONČEN")
