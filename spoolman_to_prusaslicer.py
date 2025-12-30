__version__ = "0.2"
import requests
import os
import re
import hashlib
from datetime import datetime

DEBUG = True
SPOOLMAN_URL = "http://homeassistant.local:7912/api/v1/spool"

# === WINDOWS ===
OUTPUT_DIR = os.path.expandvars(r"%APPDATA%\PrusaSlicer\filament")

# === LINUX ===
# OUTPUT_DIR = os.path.expanduser("~/.config/PrusaSlicer/filament")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==============================
# POMOCNÉ FUNKCE
# ==============================

def clean(text):
    return re.sub(r"[^\w\-_. ]", "_", str(text))

def safe_ini(text):
    return str(text).replace('"', "'").replace("\n", " ").replace("\r", " ")

def hex_to_color_name(hex_color):
    if not hex_color:
        return "Unknown"
    h = str(hex_color).lower().lstrip("#")
    # jednoduché heuristiky
    if h.endswith("ff"): 
        return "Blue"
    if h.startswith("ff"):
        return "Red"
    if "00ff00" in h or h == "00ff00": 
        return "Green"
    if "ffff00" in h or h == "ffff00":
        return "Yellow"
    if h in ("000000", "00000000"):
        return "Black"
    if h in ("ffffff", "ffffff00"):
        return "White"
    return f"HEX_{h}"

def calc_hash(data):
    return hashlib.md5(data.encode("utf-8")).hexdigest()

# ==============================
# AUTOMATICKÉ TABULKY
# ==============================

FIRST_LAYER_OFFSET = {
    "PLA": 10, "PETG": 5, "ABS": 10, "ASA": 10, "PC": 10, "TPU": 0, "NYLON": 10
}

MAX_VOLUMETRIC_SPEED = {
    "PLA": 15, "PETG": 10, "ABS": 12, "ASA": 12, "PC": 10, "TPU": 4, "NYLON": 8
}

COOLING_PROFILE = {
    "PLA": (1, 100, 100),
    "PETG": (1, 50, 80),
    "ABS": (0, 0, 0),
    "ASA": (0, 0, 0),
    "TPU": (1, 30, 60),
    "NYLON": (0, 0, 0),
}

SOLUBLE_MATERIALS = {"PVA", "BVOH", "HIPS"}

# ==============================
# START
# ==============================

print("\n=== Spoolman → PrusaSlicer SAFE SYNC ===\n")

response = requests.get(SPOOLMAN_URL, timeout=10)
response.raise_for_status()
spools = response.json()

active_spools = [s for s in spools if not s.get("archived", False)]

existing_profiles = {}
for f in os.listdir(OUTPUT_DIR):
    if f.startswith("SM_") and f.endswith(".ini"):
        existing_profiles[f] = os.path.join(OUTPUT_DIR, f)

used_profiles = set()

# ==============================
# ZPRACOVÁNÍ CÍVEK
# ==============================

for spool in active_spools:
    filament = spool.get("filament", {}) or {}

    sid = spool.get("id", "X")
    name_raw = filament.get("name", "") or ""
    name = safe_ini(name_raw)
    material = safe_ini(filament.get("material", "PLA")).upper()
    diameter = filament.get("diameter", 1.75)
    hex_color = filament.get("color_hex", "") or ""

    price = filament.get("price", 0.0) or 0.0
    density = filament.get("density", 1.24) or 1.24

    filament_weight = filament.get("weight", 0.0) or 0.0
    spool_weight = filament.get("spool_weight", 0.0) or 0.0

    initial_weight = spool.get("initial_weight", 0.0) or 0.0
    remaining_weight = spool.get("remaining_weight", 0.0) or 0.0
    used_weight = spool.get("used_weight", 0.0) or 0.0
    remaining_length = spool.get("remaining_length", 0.0) or 0.0

    article_number = safe_ini(filament.get("article_number", "") or "")
    lot_nr = safe_ini(spool.get("lot_nr", "") or "")
    location = safe_ini(spool.get("location", "") or "")
    comment = safe_ini(filament.get("comment", "") or "")

    # ==============================
    # ✅ BARVA – vylepšené rozpoznání
    # - nejdřív páruj explicitní fráze (více slov)
    # - potom hledej základní barvu jako samostatné slovo
    # - nakonec fallback na HEX
    # ==============================

    # ==============================
    # ✅ BARVA – dynamické rozpoznání efekt + barva (obě pořadí)
    # ==============================

    name_lower = name_raw.lower()

    BASIC_COLORS = [
        "white", "black", "blue", "red", "green",
        "yellow", "orange", "silver", "gold", "brown",
        "purple", "pink", "gray", "grey"
    ]

    EFFECTS = [
        "galaxy", "silk", "pearl", "metallic",
        "matte", "glossy", "luminous", "glowing", "pure"
    ]

    color = "Unknown"

    # 1) efekt + barva  (galaxy red)
    for effect in EFFECTS:
        for base in BASIC_COLORS:
            if re.search(rf"\b{effect}\s+{base}\b", name_lower):
                color = f"{effect.title()} {base.title()}"
                break
        if color != "Unknown":
            break

    # 2) barva + efekt  (red galaxy)
    if color == "Unknown":
        for base in BASIC_COLORS:
            for effect in EFFECTS:
                if re.search(rf"\b{base}\s+{effect}\b", name_lower):
                    color = f"{effect.title()} {base.title()}"
                    break
            if color != "Unknown":
                break

    # 3) pouze základní barva
    if color == "Unknown":
        for base in BASIC_COLORS:
            if re.search(rf"\b{base}\b", name_lower):
                color = base.title()
                break

    # 4) fallback – HEX heuristika
    if color == "Unknown":
        color = hex_to_color_name(hex_color)

    filament_color = f"#{hex_color.lstrip('#')}" if hex_color else "#808080"

    # TEPLOTY
    nozzle = max(170, min(int(filament.get("settings_extruder_temp", 220) or 220), 350))
    bed = max(0, min(int(filament.get("settings_bed_temp", 60) or 60), 120))

    first_layer_nozzle = filament.get(
        "settings_first_layer_extruder_temp",
        nozzle + FIRST_LAYER_OFFSET.get(material, 10)
    )

    first_layer_bed = filament.get(
        "settings_first_layer_bed_temp",
        bed
    )

    # OBJEMOVÝ PRŮTOK
    volumetric_speed = filament.get(
        "max_volumetric_speed",
        MAX_VOLUMETRIC_SPEED.get(material, 10)
    )

    # CHLAZENÍ
    cooling_profile_value = filament.get("cooling_profile", None)
    if cooling_profile_value and isinstance(cooling_profile_value, (list, tuple)) and len(cooling_profile_value) == 3:
        cooling, min_fan, max_fan = cooling_profile_value
    else:
        cooling, min_fan, max_fan = COOLING_PROFILE.get(material, (1, 50, 100))

    # ROZPUSTNOST
    filament_soluble = filament.get(
        "soluble",
        1 if material in SOLUBLE_MATERIALS else 0
    )

    # VÝROBCE
    vendor = safe_ini((filament.get("vendor") or {}).get("name", "SM"))
    vendor_safe = clean(vendor)

    # CENA
    if filament_weight > 0:
        price_per_gram = price / filament_weight
        filament_cost_per_kg = price * 1000.0 / filament_weight
    else:
        price_per_gram = 0.0
        filament_cost_per_kg = 0.0

    # ==============================
    # ✅ JEDNOŘÁDKOVÉ POZNÁMKY
    # ==============================

    filament_notes = (
        f"Vendor:{vendor} | Article:{article_number} | Lot:{lot_nr} | "
        f"Location:{location} | Filament:{filament_weight}g | "
        f"Spool:{spool_weight}g | Initial:{initial_weight}g | "
        f"Remaining:{remaining_weight}g | Used:{used_weight}g | "
        f"Length:{int(remaining_length)}mm | "
        f"Price:{price}Kc | Price/g:{price_per_gram:.4f}Kc | "
        f"Price/kg:{filament_cost_per_kg:.2f}Kc | Comment:{comment}"
    )

    # ==============================
    # NÁZEV PROFILU
    # ==============================

    profile_name = f"SM_{vendor_safe}_{material}_{color}_ID{sid}"
    safe_name = clean(profile_name)
    filename = f"{safe_name}.ini"
    path = os.path.join(OUTPUT_DIR, filename)

    # ==============================
    # ✅ FINÁLNÍ INI OBSAH – BEZ CHYB
    # ==============================

    ini_content = f"""
# Generated by Spoolman Sync on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

bed_temperature = {bed}
first_layer_bed_temperature = {first_layer_bed}
temperature = {nozzle}
first_layer_temperature = {first_layer_nozzle}

filament_type = {material}
filament_diameter = {diameter}
filament_colour = {filament_color}
filament_cost = {filament_cost_per_kg}
filament_density = {density}
filament_vendor = {vendor}
filament_spool_weight = {spool_weight}
filament_soluble = {filament_soluble}
filament_max_volumetric_speed = {volumetric_speed}

cooling = {cooling}
min_fan_speed = {min_fan}
max_fan_speed = {max_fan}

filament_notes = "{filament_notes}"

inherits = Prusament {material}
""".strip()

    used_profiles.add(filename)
    new_hash = calc_hash(ini_content)
    write_file = True

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            if calc_hash(f.read()) == new_hash:
                write_file = False
                if DEBUG:
                    print(f"ℹ️ Beze změny: {filename}")

    if write_file:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ini_content)
        print(f"✅ Uloženo: {filename}")

# ==============================
# MAZÁNÍ ZRUŠENÝCH PROFILŮ
# ==============================

for fname, fpath in existing_profiles.items():
    if fname not in used_profiles:
        os.remove(fpath)
        print(f"🗑 Smazán profil: {fname}")

print("\n🔥 HOTOVO – Restartuj PrusaSlicer")
