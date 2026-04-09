"""
STORYBOARD VISUAL ENGINE v10.6
13-Layer Consistency Engine -- Project-agnostic
All content (characters, environments) loaded from JSX storyboard files.

CHANGELOG:
- v10.6: Audit fixes — parse edit/text/source/audio fields, alias blocklist,
         char ID collision fix, word-boundary detection, 429 retry with refs,
         full pipeline L13 params, log cap, export metadata.
- v10.5: 2 presets only (Noir Faceless + Cinematic Real Faces).
         Character detection bug fixes. Style-aware character views.
         Documentary + Movie director instruction docs.
- v10.4: Layer 13 Cinematic Director AI integration into build_prompt().
         Live preview + per-section progress in UI. Version bump.
"""

import os, re, json, time, sys, base64, threading, shutil
from pathlib import Path
from datetime import datetime
import numpy as np

from google import genai
from google.genai import types
from PIL import Image, ImageDraw

# Layer 13: Cinematic Director AI
try:
    from director import inject_cinematography, get_beat_for_logging
    _HAS_DIRECTOR = True
except ImportError:
    _HAS_DIRECTOR = False

# ═══════════════════════════════════════════════════════════
# STYLE PRESETS -- Select in UI dropdown
# ═══════════════════════════════════════════════════════════

STYLE_PRESETS = {
"Noir Documentary (Faceless 3D)": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"All human characters are faceless mannequins with completely smooth heads -- "
"NO eyes, NO nose, NO mouth, NO facial features. "
"Skin is smooth matte mannequin plastic. "
"Color palette: desaturated teal and warm orange tones. "
"Lighting: dramatic single-source with volumetric god rays, deep shadows. "
"Film grain and vignette on every image. "
"16:9 widescreen. Unreal Engine 5 photorealistic PBR. "
"NEVER: cartoon, anime, 2D, text overlays, facial features. "
),
"primary": (
"3D-rendered cinematic documentary scene. "
"Faceless mannequin figures with smooth featureless heads. "
"Realistic body proportions, era-appropriate clothing with fabric detail. "
"Photorealistic PBR environment. "
"Characters in dynamic mid-action poses, never idle. "
"Cinematic 35-85mm lens, shallow depth of field, anamorphic bokeh. "
"Dramatic single-source lighting with volumetric god rays, deep shadows. "
"Desaturated teal-and-orange color grade, film grain, vignette. "
"Mood: noir-documentary, investigative, atmospheric. "
),
"secondary": (
"3D tech documentary style, premium YouTube video essay aesthetic. "
"Isometric or orthographic camera angle. "
"Smooth matte clay-like materials and soft plastics. "
"Glowing neon accents and LED lights on dark moody background. "
"Global illumination, soft shadows, ambient occlusion. "
"Abstract representation of technology, data, or infrastructure. "
"Sleek, polished, professional. Blender Cycles quality. "
"No clutter, no grime, no cartoon, no 2D. "
),
"char_base": (
"3D-rendered cinematic documentary scene. "
"Faceless mannequin figure with completely smooth head -- no eyes, nose, mouth. "
"Realistic body proportions, era-appropriate clothing with fabric detail. "
"Photorealistic PBR environment. "
"Cinematic 85mm lens, shallow depth of field, anamorphic bokeh. "
"Dramatic single-source lighting with volumetric god rays, deep shadows. "
"Desaturated teal-and-orange color grade, film grain, vignette. "
"Unreal Engine 5 quality. No cartoon, no anime, no text, no facial features. "
),
"grade": {"desat": 0.15, "teal_r": -12, "teal_g": 6, "teal_b": 15, "warm_r": 12, "warm_g": 4, "warm_b": -8, "contrast": 1.08, "vignette": 0.25, "grain": 6},
},
"Cinematic Noir (Real Faces)": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"All human characters are photorealistic humans with natural skin, real facial features, "
"natural hair, and authentic expressions. "
"Dark cinematic noir aesthetic with rich color. "
"Style reference: David Fincher, Sicario, Ozark, Mindhunter. "
"Deep shadows with teal-blue midtones and warm amber highlights. "
"Volumetric atmosphere, haze, dust in light beams. "
"Film grain and vignette on every image. "
"16:9 widescreen. Unreal Engine 5 photorealistic quality. "
"NEVER: cartoon, anime, 2D, mannequin, plastic skin, flat lighting, featureless faces. "
),
"primary": (
"Photorealistic cinematic noir scene. "
"Real human characters with natural skin texture, hair, and authentic expressions. "
"Era-appropriate clothing with fabric detail. "
"Characters in dynamic mid-action poses, never idle. "
"Cinematic 35-85mm anamorphic lens, shallow depth of field, anamorphic bokeh. "
"Dramatic single-source lighting with volumetric god rays, deep shadows. "
"Teal-blue shadows, warm amber highlights. Dark cinematic color grade. "
"Film grain, vignette. Fincher / Deakins cinematography. "
"Mood: noir-cinematic, investigative, atmospheric. "
),
"secondary": (
"Dark cinematic B-roll style. "
"Overhead or extreme close-up of objects, documents, evidence, or props. "
"Teal-blue and amber color split lighting. "
"Shallow depth of field, macro detail. "
"Premium true-crime documentary aesthetic. "
"No characters, no text in image. "
),
"char_base": (
"Photorealistic cinematic portrait. "
"Real human with natural skin texture, visible pores, stubble detail, realistic hair. "
"Authentic facial expression, lifelike eyes. "
"85mm anamorphic lens, f/1.8, shallow depth of field, creamy bokeh. "
"Fincher / Deakins lighting -- dramatic single source with deep shadows. "
"Teal-blue shadows, warm amber highlights. Dark cinematic color grade. "
"Unreal Engine 5 quality. Film grain. "
"No cartoon, no anime, no mannequin, no plastic skin, no featureless faces. "
),
"grade": {"desat": 0.10, "teal_r": -12, "teal_g": 6, "teal_b": 15, "warm_r": 12, "warm_g": 4, "warm_b": -8, "contrast": 1.12, "vignette": 0.25, "grain": 6},
},
}

# Active preset -- changed by UI dropdown
active_preset = STYLE_PRESETS["Noir Documentary (Faceless 3D)"]


def get_world_anchor():
    return active_preset["world_anchor"]


def get_primary_style():
    return active_preset["primary"]


def get_secondary_style():
    return active_preset["secondary"]


def get_char_base():
    return active_preset["char_base"]


def get_grade_params():
    return active_preset["grade"]


# ═══════════════════════════════════════════════════════════
# CHARACTER + ENVIRONMENT DEFINITIONS
# Empty by default -- populated dynamically from JSX on upload
# ═══════════════════════════════════════════════════════════

CHARACTERS = {}
ENVIRONMENTS = {}
MASTER_SHOT_DETAILS = {}


def get_char_view_prompt(cid, view):
    """Build full character ref prompt: active preset char_base + character-specific detail."""
    chars = get_active_characters()
    if cid in chars and view in chars[cid].get("views", {}):
        return get_char_base() + chars[cid]["views"][view]
    return get_char_base()


def get_char_sheet_prompt(cid):
    """Build single character reference sheet prompt -- front view, back view, close-up on one image."""
    chars = get_active_characters()
    if cid not in chars:
        return get_char_base()
    c = chars[cid]
    desc = c.get("desc", "")
    name = c.get("name", cid)
    return (
        get_char_base() +
        f"CHARACTER REFERENCE SHEET for {name}. "
        f"Three views on one image, side by side, labeled: "
        f"FRONT VIEW (full body, facing camera) | BACK VIEW (full body, facing away) | CLOSE-UP (head and shoulders portrait). "
        f"Character description: {desc}. "
        f"All three views must show the EXACT same character with identical clothing, proportions, and colors. "
        f"Clean simple background. Labels under each view. Professional character design sheet layout. "
        f"16:9 widescreen format. "
    )


def get_env_prompt(eid):
    """Build environment prompt using active preset + dynamic environment data."""
    envs = get_active_environments()
    if eid in envs:
        return get_world_anchor() + get_primary_style() + envs[eid].get("prompt_detail", envs[eid].get("prompt", ""))
    return get_world_anchor() + get_primary_style()


# ═══════════════════════════════════════════════════════════
# PARSER -- JSX storyboard to panel list
# ═══════════════════════════════════════════════════════════

def parse_storyboard(text):
    """Parse JSX storyboard -> list of panel dicts.
    Supports:
    - v1 flat: const P = [{ id, t, g, f, s, vo, ... }]
    - v2 nested: const SECTIONS = [{ id, name, panels: [{ id, type, gemini:{}, kling:{}, ... }] }]
    Returns normalized flat list with consistent field names.
    """
    # Try v2 nested format first
    sec_match = re.search(r'const\s+SECTIONS\s*=\s*\[', text)
    if sec_match:
        return _parse_v2(text)

    # Fallback: v1 flat format
    match = re.search(r'const\s+(?:P|panels)\s*=\s*\[(.*?)\];', text, re.DOTALL)
    if not match:
        return []
    panels = []
    for m in re.finditer(r'\{([^{}]+)\}', match.group(1), re.DOTALL):
        p = {}
        for sf in re.findall(r'(\w+)\s*:\s*"((?:[^"\\]|\\.)*)"', m.group(1)):
            p[sf[0]] = sf[1]
        for nf in re.findall(r'(\w+)\s*:\s*(\d+)(?!\w)', m.group(1)):
            if nf[0] not in p:
                p[nf[0]] = int(nf[1])
        if 'id' in p:
            panels.append(p)
    return panels


def _parse_v2(text):
    """Parse v2 nested SECTIONS format."""
    panels = []
    sec_start = re.search(r'const\s+SECTIONS\s*=\s*\[', text)
    if not sec_start:
        return panels

    sections_text = text[sec_start.end():]
    depth = 1
    pos = 0
    while pos < len(sections_text) and depth > 0:
        if sections_text[pos] == '[':
            depth += 1
        elif sections_text[pos] == ']':
            depth -= 1
        pos += 1
    sections_text = sections_text[:pos-1]

    section_num = 0
    for pm in re.finditer(r'panels:\s*\[', sections_text):
        obj_start = pm.start()
        brace_depth = 0
        for i in range(obj_start, -1, -1):
            if sections_text[i] == '{':
                if brace_depth == 0:
                    obj_start = i
                    break
                brace_depth -= 1
            elif sections_text[i] == '}':
                brace_depth += 1

        header_text = sections_text[obj_start:pm.start()]
        section_num += 1
        sec_name = f"Section {section_num}"
        sec_id = f"S{section_num}"

        id_m = re.search(r'id:\s*"(S\d+)"', header_text)
        name_m = re.search(r'name:\s*"([^"]+)"', header_text)
        if id_m and name_m:
            sec_id = id_m.group(1)
            sec_name = name_m.group(1)
        else:
            title_m = re.search(r'title:\s*"([^"]+)"', header_text)
            if title_m:
                sec_name = title_m.group(1)

        panels_start = pm.end()
        depth = 1
        pos = panels_start
        while pos < len(sections_text) and depth > 0:
            if sections_text[pos] == '[':
                depth += 1
            elif sections_text[pos] == ']':
                depth -= 1
            pos += 1
        panels_text_inner = sections_text[panels_start:pos-1]

        panel_objects = _extract_objects(panels_text_inner)
        for ptext in panel_objects:
            p = _parse_panel_object(ptext, sec_id, sec_name)
            if p and p.get('id'):
                panels.append(p)

    return panels


def _extract_objects(text):
    """Extract top-level { } objects from a comma-separated list, handling nesting."""
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:i+1])
                start = None
    return objects


def _parse_panel_object(ptext, sec_id, sec_name):
    """Parse a single panel object string into a normalized dict."""
    p = {'section': sec_name, 'section_id': sec_id}

    m = re.search(r'id:\s*"([^"]+)"', ptext)
    if m:
        p['id'] = m.group(1)

    m = re.search(r'type:\s*"([^"]+)"', ptext)
    if m:
        p['type'] = m.group(1)

    m = re.search(r'transition:\s*"([^"]+)"', ptext)
    if m:
        p['tr'] = m.group(1)

    m = re.search(r'(?<!\w)edit:\s*"([^"]+)"', ptext)
    if m:
        p['edit'] = m.group(1)

    m = re.search(r'(?<!\w)text:\s*"((?:[^"\\]|\\.)*)"', ptext)
    if m:
        p['text'] = m.group(1)

    m = re.search(r'music:\s*"([^"]+)"', ptext)
    if m:
        p['m'] = m.group(1)

    m = re.search(r'vo:\s*"((?:[^"\\]|\\.)*)"', ptext)
    if m:
        p['vo'] = m.group(1)

    # Audio field (Movie mode: voice actor + SFX)
    am = re.search(r'audio:\s*\{([^}]+)\}', ptext)
    if am:
        atext = am.group(1)
        vm = re.search(r'voice:\s*"([^"]*)"', atext)
        sfxm = re.search(r'sfx:\s*"((?:[^"\\]|\\.)*)"', atext)
        if vm:
            p['voice'] = vm.group(1)
        if sfxm:
            p['sfx'] = sfxm.group(1)

    # Source field (Media panels: footage sourcing notes)
    srcm = re.search(r'source:\s*\{', ptext)
    if srcm:
        # Extract the source block using brace counting
        src_start = srcm.end()
        depth = 1
        pos = src_start
        while pos < len(ptext) and depth > 0:
            if ptext[pos] == '{': depth += 1
            elif ptext[pos] == '}': depth -= 1
            pos += 1
        src_text = ptext[src_start:pos-1]
        tm = re.search(r'type:\s*"([^"]+)"', src_text)
        dm = re.search(r'description:\s*"((?:[^"\\]|\\.)*)"', src_text)
        sm = re.search(r'search:\s*"((?:[^"\\]|\\.)*)"', src_text)
        fm = re.search(r'fallback:\s*"((?:[^"\\]|\\.)*)"', src_text)
        p['source_type'] = tm.group(1) if tm else ""
        p['source_desc'] = dm.group(1) if dm else ""
        p['source_search'] = sm.group(1) if sm else ""
        p['source_fallback'] = fm.group(1) if fm else ""

    gm = re.search(r'gemini:\s*\{([^}]+)\}', ptext)
    if gm:
        gtext = gm.group(1)
        fm = re.search(r'file:\s*"([^"]+)"', gtext)
        pm2 = re.search(r'prompt:\s*"((?:[^"\\]|\\.)*)"', gtext)
        if fm:
            p['f'] = fm.group(1).replace('.png', '')
        if pm2:
            p['g'] = pm2.group(1)

    km = re.search(r'kling:\s*\{([^}]+)\}', ptext)
    if km:
        ktext = km.group(1)
        fm = re.search(r'file:\s*"([^"]+)"', ktext)
        nm = re.search(r'note:\s*"((?:[^"\\]|\\.)*)"', ktext)
        if fm:
            p['kling_file'] = fm.group(1)
        if nm:
            p['k'] = nm.group(1)

    om = re.search(r'overlay:\s*\{([^}]+)\}', ptext)
    if om:
        otext = om.group(1)
        mm = re.search(r'main:\s*"((?:[^"\\]|\\.)*)"', otext)
        sm = re.search(r'style:\s*"((?:[^"\\]|\\.)*)"', otext)
        if mm:
            p['overlay_main'] = mm.group(1)
        if sm:
            p['overlay_style'] = sm.group(1)

    hm = re.search(r'hera:\s*\[(.*?)\]', ptext, re.DOTALL)
    if hm:
        hera_text = hm.group(1)
        p['hera'] = re.findall(r'"((?:[^"\\]|\\.)*)"', hera_text)

    sm = re.search(r'(?<!\w)style:\s*"((?:[^"\\]|\\.)*)"', ptext)
    if sm and 'hera' in p:
        p['hera_style'] = sm.group(1)

    if sec_id == 'S1':
        p['co'] = 1

    return p


def get_asset_type(panel):
    """Normalize asset type for STYLE selection."""
    t = panel.get('type', panel.get('t', panel.get('assetType', ''))).lower()
    if t in ('i2v', 'parallax', 'noir') or 'noir' in t:
        return 'noir'
    elif t in ('explain', 'fern') or 'fern' in t:
        return 'fern'
    elif t == '2d' or t == 'motion':
        return '2d'
    elif 'media' in t or t == 'media':
        return 'media'
    elif t == 'transition':
        return 'transition'
    elif 'gfx' in t:
        return 'fern'
    return 'unknown'


def get_image_prompt(panel):
    """Extract the image generation prompt from panel."""
    return panel.get('g', panel.get('geminiPrompt', panel.get('prompt', '')))


def get_section(panel):
    """Get section name from panel."""
    return panel.get('section', panel.get('section_id', 'Unknown'))


# ═══════════════════════════════════════════════════════════
# AUTO-EXTRACT CHARACTERS FROM STORYBOARD
# ═══════════════════════════════════════════════════════════

_CLOTHING_WORDS = {
"suit", "jacket", "coat", "shirt", "vest", "hoodie", "coveralls", "uniform",
"boots", "shoes", "gloves", "hat", "cap", "glasses", "watch", "ring", "tie",
"turtleneck", "henley", "flannel", "corduroy", "trousers", "jeans", "pants",
"leather", "wool", "silk", "denim",
"top", "tank", "blazer", "sweater", "overcoat", "sneakers", "sandals",
"headlamp", "badge", "holster", "chain", "bracelet", "necklace",
"khakis", "slacks", "shorts",
}

_ROLE_WORDS = {
"police", "officer", "detective", "security", "guard", "agent", "inspector",
"soldier", "military", "captain", "sergeant", "lieutenant", "chief",
"banker", "clerk", "employee", "manager", "director", "boss",
"thief", "burglar", "criminal", "con", "hustler", "dealer",
"doctor", "nurse", "lawyer", "judge", "priest", "professor",
"driver", "pilot", "engineer", "mechanic", "digger", "tunneler",
"financier", "trafficker", "ringleader", "insider",
}


def auto_extract_characters(text):
    """Parse CHARACTERS array from storyboard JSX, generate aliases from descriptions.
    Returns dict compatible with engine CHARACTERS format."""
    match = re.search(r'const\s+CHARACTERS\s*=\s*\[', text)
    if not match:
        return {}

    start = match.end()
    depth = 1
    pos = start
    while pos < len(text) and depth > 0:
        if text[pos] == '[':
            depth += 1
        elif text[pos] == ']':
            depth -= 1
        pos += 1
    chars_text = text[start:pos-1]

    extracted = {}
    for obj in _extract_objects(chars_text):
        name_m = re.search(r'name:\s*"([^"]+)"', obj)
        desc_m = re.search(r'desc:\s*"([^"]+)"', obj)
        if not name_m or not desc_m:
            continue
        name = name_m.group(1)
        desc = desc_m.group(1)
        cid = _make_char_id(name)
        aliases = _extract_aliases(name, desc)
        base_desc = desc.split(". Mannequin: ")[0] if ". Mannequin: " in desc else desc
        if base_desc and not base_desc.endswith("."):
            base_desc += "."
        # Style-aware skin line: check if active preset is mannequin-based
        _anchor = active_preset.get("world_anchor", "").lower()
        _is_mannequin = any(phrase in _anchor for phrase in ["faceless mannequin", "are faceless", "smooth mannequin"])
        _skin_line = "Light-toned smooth mannequin skin." if _is_mannequin else "Natural skin texture, realistic features."
        views = {
            "front": f"CHARACTER REFERENCE -- FRONT VIEW. {base_desc} {_skin_line} Standing straight.",
            "three_quarter": f"CHARACTER REFERENCE -- 3/4 VIEW. {base_desc} {_skin_line} Slight turn.",
            "action": f"CHARACTER REFERENCE -- ACTION POSE. {base_desc} {_skin_line} In action.",
        }
        extracted[cid] = {
            "name": name,
            "alias": aliases,
            "desc": desc,
            "views": views,
        }
    return extracted


def _make_char_id(name):
    """Generate a unique character ID from full name. Project-agnostic."""
    name_lower = name.lower().strip()
    skip_words = {"the", "and", "of", "da", "de", "dos", "das", "del", "van", "von", "di"}
    words = re.sub(r'[^a-z0-9\s]', '', name_lower).split()
    significant = [w for w in words if w not in skip_words and len(w) > 1]
    if len(significant) >= 2:
        # Use first + last significant word to avoid collisions
        return f"{significant[0][:6]}_{significant[-1][:6]}"
    elif significant:
        return significant[0][:12]
    return re.sub(r'[^a-z0-9]', '', name_lower)[:12] or "char"


_ALIAS_BLOCKLIST = {
"the", "and", "of", "van", "von", "de", "da", "del", "di", "dos",
"key", "keys", "king", "camp", "guard", "money", "gold", "diamond",
"vault", "safe", "lock", "door", "gate", "alarm", "sensor", "camera",
"police", "agent", "boss", "man", "woman", "old", "young", "big",
"fast", "slow", "quick", "smart", "speed", "speedy", "monster",
"genius", "master", "angel", "ghost", "shadow", "phantom",
"black", "white", "brown", "green", "jones", "banks", "cross",
"stone", "woods", "house", "north", "south", "front", "floor",
}


def _extract_aliases(name, desc):
    """Generate detection aliases from character name and description."""
    aliases = []
    # Full name is always an alias
    full_name = name.strip()
    if full_name:
        aliases.append(full_name)

    parts = re.split(r'[\s\(\)]+', name)
    for p in parts:
        p = p.strip()
        # Single words from name: 5+ letters AND not in blocklist
        if len(p) >= 5 and p.lower() not in _ALIAS_BLOCKLIST:
            aliases.append(p)

    if "(" in name:
        before = name.split("(")[0].strip()
        inside = name.split("(")[1].rstrip(")")
        if before and before.lower() not in _ALIAS_BLOCKLIST:
            aliases.append(before)
        for w in inside.split():
            if len(w) >= 5 and w.lower() not in _ALIAS_BLOCKLIST:
                aliases.append(w)

    phrases = re.split(r'[,\.\;\-]+', desc)
    for phrase in phrases:
        phrase = phrase.strip().lower()
        words = phrase.split()
        if any(w in _CLOTHING_WORDS or w in _ROLE_WORDS for w in words) and 2 <= len(words) <= 6:
            # Skip phrases that are just blocklist words
            if not all(w in _ALIAS_BLOCKLIST or w in _ROLE_WORDS for w in words):
                aliases.append(phrase)

    desc_lower = re.sub(r'[^\w\s]', ' ', desc.lower())
    desc_words = desc_lower.split()
    for i, w in enumerate(desc_words):
        if w in _ROLE_WORDS or w in _CLOTHING_WORDS:
            if w.lower() in _ALIAS_BLOCKLIST:
                continue
            if i > 0:
                combo = f"{desc_words[i-1]} {w}"
                if len(combo) > 5:
                    aliases.append(combo)
            if i < len(desc_words) - 1:
                combo = f"{w} {desc_words[i+1]}"
                if len(combo) > 5:
                    aliases.append(combo)
            if i > 0 and i < len(desc_words) - 1:
                combo = f"{desc_words[i-1]} {w} {desc_words[i+1]}"
                if len(combo) > 8:
                    aliases.append(combo)

    seen = set()
    unique = []
    for a in aliases:
        key = a.lower().strip()
        if key not in seen and len(key) > 2 and key not in _ALIAS_BLOCKLIST:
            seen.add(key)
            unique.append(a.strip())
    return unique


_dynamic_characters = {}


def load_dynamic_characters(storyboard_text):
    """Extract characters from storyboard. Replaces hardcoded defaults completely."""
    global _dynamic_characters
    extracted = auto_extract_characters(storyboard_text)
    if extracted:
        _dynamic_characters = extracted
    else:
        _dynamic_characters = dict(CHARACTERS)
    return _dynamic_characters


def get_active_characters():
    """Return dynamic characters if loaded, else hardcoded."""
    return _dynamic_characters if _dynamic_characters else CHARACTERS


# ═══════════════════════════════════════════════════════════
# DYNAMIC ENVIRONMENT SYSTEM -- Project-agnostic
# ═══════════════════════════════════════════════════════════

_dynamic_environments = {}
_dynamic_master_shots = {}


def auto_extract_environments(text):
    """Parse ENVIRONMENTS array from storyboard JSX.
    Supports: const ENVIRONMENTS = [{ id, name, keywords, prompt }, ...]"""
    match = re.search(r'const\s+ENVIRONMENTS\s*=\s*\[', text)
    if not match:
        return {}
    start = match.end()
    depth = 1
    pos = start
    while pos < len(text) and depth > 0:
        if text[pos] == '[':
            depth += 1
        elif text[pos] == ']':
            depth -= 1
        pos += 1
    envs_text = text[start:pos-1]
    extracted = {}
    for obj in _extract_objects(envs_text):
        id_m = re.search(r'id:\s*"([^"]+)"', obj)
        name_m = re.search(r'name:\s*"([^"]+)"', obj)
        if not id_m or not name_m:
            continue
        eid = id_m.group(1)
        name = name_m.group(1)
        kw_m = re.search(r'keywords:\s*\[([^\]]+)\]', obj)
        keywords = re.findall(r'"([^"]+)"', kw_m.group(1)) if kw_m else [name.lower()]
        prompt_m = re.search(r'prompt:\s*"((?:[^"\\]|\\.)*)"', obj)
        prompt = prompt_m.group(1) if prompt_m else f"ENVIRONMENT REFERENCE. {name}. Wide 16:9. No people."
        extracted[eid] = {"name": name, "keywords": keywords, "prompt_detail": prompt}
    return extracted


def auto_detect_environments_from_panels(panels):
    """Fallback: cluster locations from panel prompts when no ENVIRONMENTS block in JSX."""
    if not panels:
        return {}
    kw_map = {
        "tunnel": (["tunnel", "underground", "shaft", "digging"], "Underground Tunnel"),
        "vault": (["vault", "safe deposit", "vault door", "vault floor"], "Bank Vault"),
        "bank_exterior": (["bank entrance", "bank building", "banco central"], "Bank Exterior"),
        "house": (["house", "bedroom", "back door", "hallway", "residential", "green house"], "Safe House"),
        "street": (["street", "sidewalk", "neighborhood", "suburban"], "Street / Neighborhood"),
        "courtroom": (["courtroom", "court", "judge", "trial", "gavel"], "Courtroom"),
        "prison": (["prison", "cell", "bars", "inmate"], "Prison"),
        "highway": (["highway", "road", "motorway", "intersection"], "Highway / Road"),
        "interrogation": (["interrogation", "police station", "surveillance"], "Police / Interrogation"),
        "dealership": (["dealership", "showroom"], "Car Dealership"),
        "rural": (["rural", "remote road", "countryside", "isolated"], "Rural / Remote"),
        "aerial": (["aerial", "skyline", "cityscape"], "Aerial / City View"),
    }
    detected = {}
    for eid, (keywords, name) in kw_map.items():
        for p in panels:
            text = (p.get('g', '') + ' ' + p.get('vo', '')).lower()
            if any(kw in text for kw in keywords):
                detected[eid] = {
                    "name": name,
                    "keywords": keywords,
                    "prompt_detail": f"ENVIRONMENT REFERENCE. {name}. Dramatic cinematic lighting. Wide 16:9 widescreen. No people.",
                }
                break
    return detected


def load_dynamic_environments(storyboard_text, panels=None):
    """Extract envs from JSX. Falls back to auto-detection from panels."""
    global _dynamic_environments, _dynamic_master_shots

    # Priority 1: Extract from JSX ENVIRONMENTS block
    extracted = auto_extract_environments(storyboard_text)
    if extracted:
        _dynamic_environments = extracted
        _dynamic_master_shots = {
            eid: f"MASTER SHOT -- HERO RENDER. {e.get('prompt_detail', e['name'])} "
                 f"Camera: wide establishing shot, cinematic composition. 16:9 widescreen. No people."
            for eid, e in extracted.items()
        }
        return _dynamic_environments

    # Priority 2: Auto-detect from panel prompts
    if panels:
        detected = auto_detect_environments_from_panels(panels)
        if detected:
            _dynamic_environments = detected
            _dynamic_master_shots = {
                eid: f"MASTER SHOT -- HERO RENDER. {e['name']}. "
                     f"Dramatic cinematic lighting, atmospheric mood. "
                     f"Camera: wide establishing shot. 16:9 widescreen. No people."
                for eid, e in detected.items()
            }
            return _dynamic_environments

    # Priority 3: Fall back to whatever is in ENVIRONMENTS (empty by default)
    _dynamic_environments = dict(ENVIRONMENTS)
    _dynamic_master_shots = dict(MASTER_SHOT_DETAILS)
    return _dynamic_environments


def get_active_environments():
    """Return dynamic environments if loaded, else hardcoded."""
    return _dynamic_environments if _dynamic_environments else ENVIRONMENTS


def get_active_master_shots():
    """Return dynamic master shots if loaded, else hardcoded."""
    return _dynamic_master_shots if _dynamic_master_shots else MASTER_SHOT_DETAILS


# ═══════════════════════════════════════════════════════════
# CHARACTER + ENV DETECTION
# ═══════════════════════════════════════════════════════════

def detect_characters(prompt, vo=""):
    """Detect characters in prompt. Returns list of char IDs.
    Uses word-boundary matching to avoid false positives."""
    text = ((prompt or "") + " " + (vo or "")).lower()
    chars = get_active_characters()
    found = []
    for cid, c in chars.items():
        for alias in c["alias"]:
            # Word boundary match to avoid substring false positives
            pattern = r'\b' + re.escape(alias.lower()) + r'\b'
            if re.search(pattern, text):
                if cid not in found:
                    found.append(cid)
                break
    return found


def detect_environment(prompt, vo=""):
    """Detect environment/location using dynamic ENVIRONMENTS."""
    text = ((prompt or "") + " " + (vo or "")).lower()
    envs = get_active_environments()
    for eid, env in envs.items():
        for kw in env.get("keywords", []):
            if kw.lower() in text:
                return eid
    return None


def count_words(text):
    return len(text.split()) if text else 0


# ═══════════════════════════════════════════════════════════
# PROMPT BUILDING
# ═══════════════════════════════════════════════════════════

def build_prompt(panel, char_id=None, env_id=None, all_chars=None,
                 section_name="", panel_index=0, section_total=20,
                 is_first_in_section=False):
    """Build generation prompt: ANCHOR + L13_CINEMA + CHAR_REF + ENV_REF + STYLE + SCENE.
    Layer 8: all_chars = list of ALL character IDs in this panel.
    Layer 13: Cinematic Director AI injection (camera, lens, lighting, composition)."""
    scene_prompt = get_image_prompt(panel)
    asset = get_asset_type(panel)
    style = get_primary_style() if asset == 'noir' else get_secondary_style()

    # Layer 13: Cinematic Director AI — inject camera/lens/lighting/composition
    cinema_str = ""
    if _HAS_DIRECTOR and asset == 'noir':
        vo = panel.get('vo', '')
        cinema_str = inject_cinematography(
            vo, scene_prompt, section_name,
            panel_index, section_total, is_first_in_section
        )

    char_str = ""
    chars = get_active_characters()
    char_ids = all_chars or ([char_id] if char_id else [])
    char_ids = [c for c in char_ids if c and c in chars]
    if char_ids and asset != 'fern':
        if len(char_ids) == 1:
            char_str = (
                f"SUBJECT CONSISTENCY: The character in this scene is {chars[char_ids[0]]['name']}. "
                f"You MUST match the provided character reference sheet EXACTLY -- same clothing, "
                f"same build, same proportions, same colors. Do NOT deviate. "
            )
        else:
            names = [chars[c]['name'] for c in char_ids]
            char_str = (
                f"SUBJECT CONSISTENCY: This scene contains {len(char_ids)} characters: {', '.join(names)}. "
                f"Reference sheets are provided for each. Match EVERY character EXACTLY to their "
                f"reference -- same clothing, build, proportions, colors. Each character must be "
                f"visually distinct and match their own reference sheet. "
            )

    env_str = ""
    envs = get_active_environments()
    if env_id and env_id in envs:
        env_str = (
            f"ENVIRONMENT CONSISTENCY: This scene takes place in {envs[env_id]['name']}. "
            f"Maintain visual consistency with the environment reference image. "
        )

    return get_world_anchor() + cinema_str + char_str + env_str + style + scene_prompt


# ═══════════════════════════════════════════════════════════
# CONFIG FILE -- saves API key + settings
# ═══════════════════════════════════════════════════════════

CONFIG_FILE = Path("storyboard_config.json")


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except:
            pass
    return {}


def save_config(data):
    existing = load_config()
    existing.update(data)
    CONFIG_FILE.write_text(json.dumps(existing, indent=2))


image_settings = {
    "resolution": "2K (recommended)",
    "aspect_ratio": "16:9",
    "model": "gemini-3-pro-image-preview",
}

MODEL_OPTIONS = {
    "Nano Banana Pro (Best)": "gemini-3-pro-image-preview",
    "Nano Banana 2 (Fast)": "gemini-3.1-flash-image-preview",
}

RESOLUTION_MAP = {
    "1K (fast, draft)": "1K",
    "2K (recommended)": "2K",
    "4K (production)": "4K",
}

AR_OPTIONS = ["16:9", "9:16", "4:3", "3:4", "1:1", "21:9"]


# ═══════════════════════════════════════════════════════════
# API GENERATION
# ═══════════════════════════════════════════════════════════

def get_config():
    ar = image_settings.get("aspect_ratio", "16:9")
    res_label = image_settings.get("resolution", "2K (recommended)")
    res_val = RESOLUTION_MAP.get(res_label, "2K")
    try:
        return types.GenerateContentConfig(
            response_modalities=['IMAGE', 'TEXT'],
            image_config=types.ImageConfig(
                aspect_ratio=ar,
                image_size=res_val,
                output_compression_quality=100,
            )
        )
    except:
        return types.GenerateContentConfig(
            response_modalities=['IMAGE', 'TEXT'],
            image_config=types.ImageConfig(aspect_ratio=ar)
        )


def extract_image(response):
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            d = part.inline_data.data
            return base64.b64decode(d) if isinstance(d, str) else d
    return None


def get_active_model():
    return image_settings.get("model", "gemini-3.1-flash-image-preview")


def _resize_for_api(img, max_size=768):
    """Resize image for API payload. Keeps aspect ratio, caps at max_size px on longest side."""
    if max(img.size) > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img


def gen_single(client, prompt, ref_paths=None, max_retries=3):
    contents = []
    if ref_paths:
        for rp in ref_paths:
            if Path(rp).exists():
                contents.append(_resize_for_api(Image.open(rp)))
    contents.append(prompt)
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=get_active_model(), contents=contents, config=get_config()
            )
            adaptive_delay.success()
            return extract_image(resp)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                adaptive_delay.rate_limited()
                wait = 30 * (attempt + 1)
                time.sleep(wait)
                continue
            raise


# ═══════════════════════════════════════════════════════════
# ADAPTIVE DELAY
# ═══════════════════════════════════════════════════════════

class AdaptiveDelay:
    """Start at 1s. If 429 hit, bump to 4s. Ease back down after consecutive successes."""
    def __init__(self):
        self.delay = 1.0
        self.min_delay = 1.0
        self.max_delay = 6.0
        self.successes = 0

    def wait(self):
        time.sleep(self.delay)

    def success(self):
        self.successes += 1
        if self.successes >= 5 and self.delay > self.min_delay:
            self.delay = max(self.min_delay, self.delay * 0.7)
            self.successes = 0

    def rate_limited(self):
        self.delay = min(self.max_delay, self.delay * 2)
        self.successes = 0


adaptive_delay = AdaptiveDelay()


def gen_chat_section(client, section_name, panels_data, callback=None, chat_reset_interval=12):
    """Generate panels in a section using chat for visual memory.
    Resets chat every chat_reset_interval panels to prevent context overflow."""
    results = {}
    RESET_EVERY = chat_reset_interval
    panels_since_reset = 0
    chat = None

    def _new_chat():
        nonlocal chat
        chat = client.chats.create(model=get_active_model())
        try:
            chat.send_message(
                f"You are generating a cinematic documentary storyboard. "
                f"Section: {section_name}. {get_world_anchor()} "
                f"Maintain absolute visual consistency across all images."
            )
        except:
            pass

    try:
        _new_chat()

        for pd in panels_data:
            if pd.get("stop"):
                break
            pid = pd["id"]
            out_path = Path(pd["output"])

            if out_path.exists():
                if callback:
                    callback("skip", pid)
                results[pid] = True
                continue

            # Reset chat to prevent context overflow
            if panels_since_reset >= RESET_EVERY:
                try:
                    _new_chat()
                    panels_since_reset = 0
                    if callback:
                        callback("generating", pid, "fresh chat")
                except Exception as e:
                    if callback:
                        callback("warn", pid, f"chat reset failed: {str(e)[:40]}")

            if callback:
                callback("generating", pid, pd.get("info", ""))

            try:
                contents = []
                for rp in pd.get("refs", []):
                    if Path(rp).exists():
                        contents.append(_resize_for_api(Image.open(rp)))
                    if len(contents) >= 3:
                        break
                contents.append(pd["prompt"])

                resp = chat.send_message(contents, config=get_config())
                adaptive_delay.success()
                img = extract_image(resp)
                if img:
                    out_path.write_bytes(img)
                    results[pid] = True
                    panels_since_reset += 1
                    if callback:
                        callback("ok", pid)
                else:
                    results[pid] = False
                    if callback:
                        callback("warn", pid)

            except Exception as e:
                if "429" in str(e):
                    adaptive_delay.rate_limited()
                    time.sleep(30)
                    try:
                        # Retry with full refs to maintain consistency layers
                        contents2 = []
                        for rp in pd.get("refs", []):
                            if Path(rp).exists():
                                contents2.append(_resize_for_api(Image.open(rp)))
                            if len(contents2) >= 3:
                                break
                        contents2.append(pd["prompt"])
                        resp2 = chat.send_message(contents2, config=get_config())
                        img2 = extract_image(resp2)
                        if img2:
                            out_path.write_bytes(img2)
                            results[pid] = True
                            panels_since_reset += 1
                            if callback:
                                callback("ok", pid)
                            continue
                    except:
                        pass
                results[pid] = False
                if callback:
                    callback("fail", pid, str(e)[:80])

            adaptive_delay.wait()

    except Exception as e:
        if callback:
            callback("fail", "section", str(e)[:80])

    return results


# ═══════════════════════════════════════════════════════════
# POST-PROCESSING -- Color grade
# ═══════════════════════════════════════════════════════════

def post_process(img_path, out_path=None):
    """Apply cinematic color grade: teal-orange, contrast, vignette, grain."""
    if out_path is None:
        out_path = img_path
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    grade = get_grade_params()

    # Desaturation
    desat = grade.get("desat", 0.15)
    gray = np.mean(arr, axis=2, keepdims=True)
    arr = arr * (1 - desat) + gray * desat

    # Teal-orange split toning
    luminance = np.mean(arr, axis=2, keepdims=True) / 255.0
    shadows = 1.0 - luminance
    highlights = luminance
    arr[:, :, 0] += grade.get("teal_r", -12) * shadows[:, :, 0] + grade.get("warm_r", 12) * highlights[:, :, 0]
    arr[:, :, 1] += grade.get("teal_g", 6) * shadows[:, :, 0] + grade.get("warm_g", 4) * highlights[:, :, 0]
    arr[:, :, 2] += grade.get("teal_b", 15) * shadows[:, :, 0] + grade.get("warm_b", -8) * highlights[:, :, 0]

    # Contrast
    contrast = grade.get("contrast", 1.08)
    arr = (arr - 128) * contrast + 128

    # Vignette
    vig = grade.get("vignette", 0.25)
    if vig > 0:
        h, w = arr.shape[:2]
        Y, X = np.ogrid[:h, :w]
        cx, cy = w / 2, h / 2
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        max_dist = np.sqrt(cx ** 2 + cy ** 2)
        vignette_mask = 1 - vig * (dist / max_dist) ** 2
        arr *= vignette_mask[:, :, np.newaxis]

    # Film grain
    grain_amount = grade.get("grain", 6)
    if grain_amount > 0:
        noise = np.random.normal(0, grain_amount, arr.shape).astype(np.float32)
        arr += noise

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(out_path, quality=95)


# ═══════════════════════════════════════════════════════════
# MASTER SHOT PROMPTS -- dynamic
# ═══════════════════════════════════════════════════════════

def get_master_shot_prompt(eid):
    """Build master shot prompt using active preset + dynamic data."""
    details = get_active_master_shots()
    detail = details.get(eid, "")
    if not detail:
        envs = get_active_environments()
        if eid in envs:
            env = envs[eid]
            detail = (
                f"MASTER SHOT -- HERO RENDER. {env.get('prompt_detail', env.get('prompt', ''))} "
                f"Camera: wide establishing shot, cinematic composition. 16:9 widescreen. No people."
            )
        else:
            return get_env_prompt(eid)
    return get_world_anchor() + get_primary_style() + detail


# ═══════════════════════════════════════════════════════════
# L7: VISUAL MEMORY BANK
# ═══════════════════════════════════════════════════════════

class VisualMemoryBank:
    """Tracks the latest successful render for each character and environment.
    Layer 10: Also tracks section bridge frames for cross-section continuity."""

    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.bank_file = self.output_dir / "memory_bank.json"
        self.char_latest = {}
        self.env_latest = {}
        self.section_last = {}
        self.load()

    def load(self):
        if self.bank_file.exists():
            try:
                data = json.loads(self.bank_file.read_text())
                self.char_latest = data.get("char_latest", {})
                self.env_latest = data.get("env_latest", {})
                self.section_last = data.get("section_last", {})
                self.char_latest = {k: v for k, v in self.char_latest.items() if Path(v).exists()}
                self.env_latest = {k: v for k, v in self.env_latest.items() if Path(v).exists()}
                self.section_last = {k: v for k, v in self.section_last.items() if Path(v).exists()}
            except:
                pass

    def save(self):
        self.bank_file.write_text(json.dumps({
            "char_latest": self.char_latest,
            "env_latest": self.env_latest,
            "section_last": self.section_last,
        }, indent=2))

    def update_char(self, cid, scene_path):
        if Path(scene_path).exists():
            self.char_latest[cid] = str(scene_path)
            self.save()

    def update_env(self, eid, scene_path):
        if Path(scene_path).exists():
            self.env_latest[eid] = str(scene_path)
            self.save()

    def update_section(self, section_name, scene_path):
        if Path(scene_path).exists():
            self.section_last[section_name] = str(scene_path)
            self.save()

    def get_previous_section_bridge(self, current_section, section_order):
        if not section_order:
            return None
        try:
            idx = section_order.index(current_section)
            if idx > 0:
                prev = section_order[idx - 1]
                if prev in self.section_last:
                    return self.section_last[prev]
        except (ValueError, IndexError):
            pass
        return None

    def get_char_refs(self, cid, portrait_refs):
        refs = list(portrait_refs)
        if cid in self.char_latest:
            latest = self.char_latest[cid]
            if latest not in refs:
                refs.append(latest)
        return refs[:3]

    def get_env_ref(self, eid, master_shot_path, env_ref_path=None):
        refs = []
        if master_shot_path and Path(master_shot_path).exists():
            refs.append(master_shot_path)
        elif env_ref_path and Path(env_ref_path).exists():
            refs.append(env_ref_path)
        if eid in self.env_latest:
            latest = self.env_latest[eid]
            if latest not in refs:
                refs.append(latest)
        return refs[:2]


# ═══════════════════════════════════════════════════════════
# LAYER 9: STYLE ANCHOR
# ═══════════════════════════════════════════════════════════

def get_style_anchor_prompt():
    """Generate a style key image. Uses first environment if available."""
    envs = get_active_environments()
    if envs:
        first_env = next(iter(envs.values()))
        env_desc = first_env.get("prompt_detail", first_env.get("prompt", ""))[:200]
    else:
        env_desc = (
            "A dimly lit interior space, cold blue-gray tones, dramatic single-source "
            "overhead lighting, atmospheric dust particles in light beams."
        )
    return (
        get_world_anchor() +
        get_primary_style() +
        f"STYLE KEY IMAGE: Generate a single establishing shot that defines the visual "
        f"style of this entire project. {env_desc} "
        f"This image sets the tone for every frame that follows. Cinematic, moody, premium. "
        f"16:9 widescreen. No characters -- environment only. "
    )


# ═══════════════════════════════════════════════════════════
# LAYER 11: CONSISTENCY SCORING
# ═══════════════════════════════════════════════════════════

def score_consistency(client, generated_path, ref_paths, panel_desc=""):
    """Score how well a generated image matches its references.
    Uses Gemini vision to compare. Returns score 0-100 and feedback."""
    try:
        contents = []
        contents.append(
            "CONSISTENCY EVALUATION: Compare the FIRST image (generated scene) against "
            "the REFERENCE images that follow. Score how well the generated scene "
            "matches the references on these criteria:\n"
            "1. Character appearance (clothing, build, proportions)\n"
            "2. Environment consistency (lighting, architecture, mood)\n"
            "3. Style consistency (color palette, contrast, atmosphere)\n\n"
            'Respond with ONLY a JSON object: {"score": <0-100>, "issues": "<brief description>"}\n'
            "Score 80+ = good match, 60-79 = acceptable, below 60 = needs redo."
        )

        if Path(generated_path).exists():
            contents.append(_resize_for_api(Image.open(generated_path)))
        else:
            return 100, "No image to score"

        for rp in ref_paths[:3]:
            if Path(rp).exists():
                contents.append(_resize_for_api(Image.open(rp)))

        if len(contents) < 3:
            return 100, "Not enough refs to score"

        resp = client.models.generate_content(
            model=get_active_model().replace("-image-preview", ""),
            contents=contents
        )

        text = ""
        for part in resp.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                text = part.text.strip()
                break

        score_match = re.search(r'"score"\s*:\s*(\d+)', text)
        issues_match = re.search(r'"issues"\s*:\s*"([^"]*)"', text)
        score = int(score_match.group(1)) if score_match else 75
        issues = issues_match.group(1) if issues_match else "Could not parse"
        return min(100, max(0, score)), issues

    except Exception as e:
        return 75, f"Score error: {str(e)[:60]}"


# ═══════════════════════════════════════════════════════════
# LAYER 12: ADAPTIVE PROMPTING
# ═══════════════════════════════════════════════════════════

def build_adaptive_prompt(original_prompt, score, issues, attempt=1):
    """Add correction instructions when consistency score is low."""
    if score >= 70:
        return original_prompt

    severity = "CRITICAL" if score < 50 else "IMPORTANT"
    correction = (
        f"\n\n[{severity} CORRECTION -- Attempt {attempt+1}]: "
        f"The previous generation scored {score}/100 on consistency. "
        f"Issues: {issues}. "
    )

    if score < 50:
        correction += (
            "You MUST fix this. Match the reference images EXACTLY. "
            "Same clothing. Same body type. Same proportions. Same colors. "
            "Same lighting mood. Do NOT improvise or deviate from the references. "
            "This is a strict visual match requirement. "
        )
    else:
        correction += (
            "Please improve consistency with the reference images. "
            "Pay closer attention to character clothing details and environment lighting. "
        )

    return original_prompt + correction
