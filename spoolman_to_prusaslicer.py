import requests
import os
import re

SPOOLMAN_URL = "http://homeassistant.local:7912/api/v1/spool"

# === ZMĚŇ PODLE SYSTÉMU ===

# Windows:
OUTPUT_DIR = os.path.expandvars(r"%APPDATA%\PrusaSlicer\filament")

# Linux:
# OUTPUT_DIR = os.path.expanduser("~/.config/PrusaSlicer/filament")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def clean(text):
    return re.sub(r'[^\w\-_. ]', '_', text)

response = requests.get(SPOOLMAN_URL, timeout=10)
spools = response.json()

for spool in spools:
    sid = spool.get("id", "X")
    material = spool.get("filament_type", "PLA")
    color = spool.get("color", "Unknown")
    diameter = spool.get("diameter", 1.75)
    nozzle = spool.get("nozzle_temp", 220)
    bed = spool.get("bed_temp", 60)
    vendor = spool.get("vendor", "Spoolman")

    profile_name = f"Spoolman_{material}_{color}_ID{sid}"
    safe_name = clean(profile_name)

    ini = f"""
[filament:{profile_name}]
filament_type = {material}
filament_diameter = {diameter}
temperature = {nozzle}
bed_temperature = {bed}
filament_vendor = {vendor}
    """.strip()

    path = os.path.join(OUTPUT_DIR, f"{safe_name}.ini")

    with open(path, "w", encoding="utf-8") as f:
        f.write(ini)

    print(f"✅ Vytvořen profil: {profile_name}")

print("\n🔥 HOTOVO – restartuj PrusaSlicer.")