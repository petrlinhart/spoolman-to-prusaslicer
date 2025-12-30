__version__ = "0.3"
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
# ROZŠÍŘENÉ DEFINICE PRO BARVY
# ==============================

BASIC_COLORS = [
    "white", "black", "blue", "red", "green",
    "yellow", "orange", "silver", "gold", "brown",
    "purple", "pink", "gray", "grey", "cyan",
    "magenta", "violet", "turquoise", "beige", "cream",
    "navy", "teal", "maroon", "olive", "coral",
    "bronze", "copper", "champagne", "ivory", "mint",
    "lavender", "peach", "salmon", "burgundy", "charcoal",
    "natural", "transparent", "clear"
]

# Efekty filamentů (Silk, Galaxy, atd.)
EFFECTS = [
    "silk", "galaxy", "pearl", "metallic", "matte", "glossy",
    "luminous", "glowing", "pure", "sparkle", "glitter",
    "rainbow", "chameleon", "marble", "wood", "carbon",
    "glow-in-dark", "glow in the dark", "gitd", "fluorescent",
    "dual-color", "dual color", "dualcolor", "tri-color", 
    "tri color", "tricolor", "multi-color", "multicolor",
    "gradient", "transition", "coextruded"
]

# Aliasy pro normalizaci názvů barev
COLOR_ALIASES = {
    "grey": "gray",
    "transparent": "clear",
}

def normalize_color(color):
    """Normalizuje název barvy (např. grey -> gray)"""
    return COLOR_ALIASES.get(color.lower(), color)

def extract_color_info(name_raw):
    """
    Extrahuje informace o barvě z názvu filamentu.
    Podporuje:
    - Jednobarevné: "Red", "Blue"
    - S efektem: "Silk Red", "Galaxy Blue"  
    - Dual-color: "Dual-Color Red Green", "Red-Green"
    - Tri-color: "Tri-Color Red Blue Green"
    - Kombinace: "Silk Dual-Color Red Green"
    
    Vrací tuple: (display_name, short_name)
    - display_name: plný název pro zobrazení ("Silk Dual Red-Green")
    - short_name: zkrácený název pro filename ("SilkDual_Red-Green")
    """
    name_lower = name_raw.lower()
    
    detected_effects = []
    detected_colors = []
    is_multicolor = False
    multicolor_type = None  # "dual", "tri", "multi", "gradient"
    
    # 1) Detekce typu vícebarevnosti
    multicolor_patterns = [
        (r"dual[- ]?colou?r", "dual"),
        (r"tri[- ]?colou?r", "tri"),
        (r"multi[- ]?colou?r", "multi"),
        (r"gradient", "gradient"),
        (r"transition", "gradient"),
        (r"coextruded", "dual"),
        (r"rainbow", "rainbow"),
        (r"chameleon", "chameleon"),
    ]
    
    for pattern, mc_type in multicolor_patterns:
        if re.search(pattern, name_lower):
            is_multicolor = True
            multicolor_type = mc_type
            break
    
    # 2) Detekce efektů (Silk, Galaxy, atd.)
    for effect in EFFECTS:
        # Přeskočíme multicolor patterny, ty už máme
        if effect in ["dual-color", "dual color", "dualcolor", 
                      "tri-color", "tri color", "tricolor",
                      "multi-color", "multicolor", "gradient", 
                      "transition", "coextruded", "rainbow", "chameleon"]:
            continue
        if re.search(rf"\b{re.escape(effect)}\b", name_lower):
            detected_effects.append(effect.title())
    
    # 3) Detekce barev
    # Nejdřív zkusíme najít vzory jako "Red Green", "Red-Green", "Red/Green"
    color_sequence_pattern = r'\b(' + '|'.join(BASIC_COLORS) + r')(?:[\s\-/&]+(' + '|'.join(BASIC_COLORS) + r'))+\b'
    color_sequences = re.findall(color_sequence_pattern, name_lower)
    
    if color_sequences:
        # Máme sekvenci barev
        # Najdeme všechny barvy v pořadí
        all_colors_in_name = re.findall(r'\b(' + '|'.join(BASIC_COLORS) + r')\b', name_lower)
        # Odstraníme duplikáty při zachování pořadí
        seen = set()
        for c in all_colors_in_name:
            normalized = normalize_color(c)
            if normalized not in seen:
                detected_colors.append(normalized.title())
                seen.add(normalized)
    else:
        # Hledáme jednotlivé barvy
        for base in BASIC_COLORS:
            if re.search(rf"\b{base}\b", name_lower):
                normalized = normalize_color(base)
                if normalized.title() not in detected_colors:
                    detected_colors.append(normalized.title())
    
    # 4) Automatická detekce multicolor pokud máme více barev
    if len(detected_colors) >= 2 and not is_multicolor:
        is_multicolor = True
        if len(detected_colors) == 2:
            multicolor_type = "dual"
        elif len(detected_colors) == 3:
            multicolor_type = "tri"
        else:
            multicolor_type = "multi"
    
    # 5) Sestavení výsledného názvu
    parts = []
    short_parts = []
    
    # Efekty
    if detected_effects:
        parts.extend(detected_effects)
        short_parts.append("".join(detected_effects))
    
    # Typ vícebarevnosti
    if is_multicolor and multicolor_type:
        type_names = {
            "dual": "Dual",
            "tri": "Tri", 
            "multi": "Multi",
            "gradient": "Gradient",
            "rainbow": "Rainbow",
            "chameleon": "Chameleon"
        }
        mc_name = type_names.get(multicolor_type, "Multi")
        parts.append(mc_name)
        short_parts.append(mc_name)
    
    # Barvy
    if detected_colors:
        if is_multicolor:
            color_str = "-".join(detected_colors)
            parts.append(color_str)
            short_parts.append(color_str)
        else:
            parts.extend(detected_colors)
            short_parts.extend(detected_colors)
    
    # Fallback
    if not parts:
        return ("Unknown", "Unknown")
    
    display_name = " ".join(parts)
    short_name = "_".join(short_parts).replace(" ", "")
    
    return (display_name, short_name)

# ==============================
# START
# ==============================

print("\n=== Spoolman → PrusaSlicer SAFE SYNC v0.3 ===")
print("    (s podporou vícebarevných filamentů)\n")

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
    # ✅ BARVA – vylepšené rozpoznání s multicolor podporou
    # ==============================
    
    color_display, color_short = extract_color_info(name_raw)
    
    # Fallback na HEX pokud nic nebylo nalezeno
    if color_display == "Unknown":
        color_display = hex_to_color_name(hex_color)
        color_short = color_display.replace(" ", "_")

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
        f"Price/kg:{filament_cost_per_kg:.2f}Kc | "
        f"Color:{color_display} | Comment:{comment}"
    )

    # ==============================
    # NÁZEV PROFILU
    # ==============================

    profile_name = f"SM_{vendor_safe}_{material}_{color_short}_ID{sid}"
    safe_name = clean(profile_name)
    filename = f"{safe_name}.ini"
    path = os.path.join(OUTPUT_DIR, filename)

    # ==============================
    # ✅ FINÁLNÍ INI OBSAH
    # ==============================

    ini_content = f"""
# Generated by Spoolman Sync v{__version__} on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Color: {color_display}

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
                    print(f"ℹ️  Beze změny: {filename}")

    if write_file:
        with open(path, "w", encoding="utf-8") as f:
            f.write(ini_content)
        print(f"✅ Uloženo: {filename}")
        if DEBUG:
            print(f"   └─ Barva: {color_display}")

# ==============================
# MAZÁNÍ ZRUŠENÝCH PROFILŮ
# ==============================

for fname, fpath in existing_profiles.items():
    if fname not in used_profiles:
        os.remove(fpath)
        print(f"🗑  Smazán profil: {fname}")

print("\n🔥 HOTOVO – Restartuj PrusaSlicer")


# ==============================
# TEST FUNKCE (pro debug)
# ==============================

if __name__ == "__main__" and DEBUG:
    print("\n" + "="*50)
    print("TEST ROZPOZNÁVÁNÍ BAREV:")
    print("="*50)
    
    test_names = [
        "ERYONE - Silk PLA Dual-Color Red Green - PLA",
        "Prusament PLA Galaxy Black",
        "eSUN Silk PLA Gold",
        "Polymaker PolyTerra PLA Marble White",
        "SUNLU Rainbow PLA",
        "Eryone Tri-Color Blue Red Yellow",
        "Generic Red-Green Filament",
        "Silk Dual Red/Blue PLA",
        "Prusament PETG Orange",
        "eSUN PLA+ Glow-in-Dark Green",
        "Bambu Lab PLA Matte Charcoal",
        "Overture Silk Purple Gold",
        "TTYT3D Silk Dual-Color Copper Silver",
        "Geeetech Silk PLA Red",
    ]
    
    for name in test_names:
        display, short = extract_color_info(name)
        print(f"  '{name}'")
        print(f"    → Display: {display}")
        print(f"    → Short:   {short}")
        print()
