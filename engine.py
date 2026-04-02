"""
STORYBOARD VISUAL ENGINE v10.4
13-Layer Consistency Engine -- Project-agnostic
All content (characters, environments) loaded from JSX storyboard files.

CHANGELOG:
- v10.4: Layer 13 Cinematic Director AI integration into build_prompt().
         Live preview + per-section progress in UI. Version bump.
- v10.3: Smart detection, aggressive auto-redo, body type injection,
         section color palette lock, panel-to-panel continuity scoring.
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
"Photorealistic Documentary": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Photorealistic photography style. Real human faces with natural expressions. "
"Shot on ARRI Alexa Mini, Zeiss Master Prime lenses. "
"Natural color grade, slight desaturation. "
"Documentary cinematography -- observational, intimate, authentic. "
"16:9 widescreen. High dynamic range. "
"NEVER: cartoon, anime, 3D render look, plastic skin, mannequin. "
),
"primary": (
"Photorealistic documentary photograph. Real human with natural skin texture and features. "
"ARRI Alexa Mini, 35-85mm Zeiss Master Prime, shallow depth of field. "
"Natural single-source lighting -- practical lights, window light, overhead fluorescent. "
"Muted color palette, slight blue shadows, warm highlights. "
"Mood: intimate, observational, journalistic. "
),
"secondary": (
"Clean photographic infographic style. "
"Shot from above on dark surface -- objects arranged for explanation. "
"Soft even lighting, minimal shadows. "
"Educational, clear, premium documentary B-roll aesthetic. "
),
"char_base": (
"Photorealistic portrait photograph. Real human with natural skin, hair, and facial features. "
"ARRI Alexa Mini, 85mm lens, f/2.0, shallow depth of field. "
"Natural studio lighting -- soft key light, subtle fill, dark background. "
"Muted documentary color grade. No cartoon, no 3D render look. "
),
"grade": {"desat": 0.08, "teal_r": -5, "teal_g": 3, "teal_b": 8, "warm_r": 6, "warm_g": 2, "warm_b": -4, "contrast": 1.05, "vignette": 0.20, "grain": 4},
},
"Anime Documentary": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Japanese anime art style. 2D hand-drawn aesthetic with cel shading. "
"Characters have expressive anime faces -- large eyes, detailed hair, emotional expressions. "
"Backgrounds are detailed painted environments. "
"16:9 widescreen. Studio Bones / MAPPA quality animation frames. "
"NEVER: 3D render, photorealistic, clay, pixel art, western cartoon. "
),
"primary": (
"Anime key frame illustration. Japanese animation studio quality. "
"Dramatic anime cinematography -- dynamic angles, speed lines where appropriate. "
"Rich painted backgrounds with atmospheric depth. "
"Cel-shaded characters with detailed clothing and expressive body language. "
"Dramatic anime lighting -- rim lights, color-coded shadows, lens flares. "
"Mood: intense, cinematic, emotionally charged. "
),
"secondary": (
"Anime explainer style. Clean chibi or simplified character proportions. "
"Whiteboard or chalkboard aesthetic with hand-drawn diagrams. "
"Soft pastel colors, clear visual hierarchy. "
"Educational anime aesthetic -- think Cells at Work or Dr. Stone explanation scenes. "
),
"char_base": (
"Anime character design sheet. Japanese animation studio quality. "
"Full body front view and 3/4 view side by side. "
"Detailed anime face -- distinctive eye color and shape, unique hairstyle. "
"Era-appropriate costume with fabric detail and accessories. "
"Clean lines, cel shading, neutral background. "
),
"grade": {"desat": 0.0, "teal_r": 0, "teal_g": 0, "teal_b": 0, "warm_r": 0, "warm_g": 0, "warm_b": 0, "contrast": 1.10, "vignette": 0.10, "grain": 0},
},
"Comic Book / Graphic Novel": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Western comic book art style. Bold ink lines, halftone dot shading. "
"Characters have stylized but realistic proportions -- not chibi, not hyper-real. "
"Strong blacks, limited color palette with flat colors and dramatic shadows. "
"16:9 widescreen panel composition. DC/Marvel graphic novel quality. "
"NEVER: anime, photorealistic, 3D render, watercolor, pixel art. "
),
"primary": (
"Comic book panel illustration. Bold ink outlines, halftone dot shading. "
"Dramatic noir-influenced composition -- deep shadows, stark contrasts. "
"Limited color palette -- 4-5 colors per scene maximum. "
"Dynamic poses and dramatic camera angles. "
"Style reference: Sean Phillips, Alex Maleev, David Mazzucchelli. "
"Mood: gritty, noir, graphic. "
),
"secondary": (
"Comic book infographic panel. Blueprint aesthetic with technical cross-section views. "
"White lines on dark blue background. Callout labels and arrows. "
"Clean technical illustration meets comic book aesthetic. "
),
"char_base": (
"Comic book character design. Bold ink outlines, flat color fills. "
"Front view and 3/4 view side by side. "
"Stylized but anatomically correct proportions. "
"Distinctive silhouette and costume design. Strong shadow shapes. "
"Halftone shading. Neutral background. Graphic novel quality. "
),
"grade": {"desat": 0.05, "teal_r": -8, "teal_g": 0, "teal_b": 10, "warm_r": 8, "warm_g": 2, "warm_b": -6, "contrast": 1.15, "vignette": 0.15, "grain": 3},
},
"Cyberpunk Neon Noir": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Cyberpunk neon noir aesthetic. Rain-soaked futuristic city. "
"Characters have augmented cybernetic features mixed with streetwear. "
"Dominant colors: electric blue, hot pink, toxic green neon against dark backgrounds. "
"Holographic UI elements floating in environment. "
"16:9 widescreen. Unreal Engine 5 quality. "
"NEVER: daylight, cartoon, clean/sterile, natural environments. "
),
"primary": (
"Cyberpunk cinematic scene. Rain-soaked streets, neon reflections on wet asphalt. "
"Volumetric fog and atmospheric haze. Holographic advertisements in background. "
"Cinematic 35mm anamorphic lens, extreme depth. "
"Dominant neon blue and pink lighting with deep shadows. "
"Blade Runner meets Ghost in the Shell meets Akira aesthetic. "
"Mood: dystopian, noir, electric. "
),
"secondary": (
"Cyberpunk holographic UI explainer. Floating translucent data visualizations. "
"Wireframe 3D models with neon edge lighting on dark void background. "
"Sci-fi tech aesthetic -- think Minority Report UI or Iron Man HUD. "
),
"char_base": (
"Cyberpunk character design. Neon-lit portrait against dark rain-soaked backdrop. "
"Front view and 3/4 view side by side. "
"Streetwear mixed with cybernetic augmentations. "
"Neon rim lighting, wet surface reflections. "
"Detailed face with cyber-enhancements. Blade Runner 2049 aesthetic. "
),
"grade": {"desat": 0.0, "teal_r": -15, "teal_g": 5, "teal_b": 20, "warm_r": 15, "warm_g": -5, "warm_b": 10, "contrast": 1.12, "vignette": 0.30, "grain": 5},
},
"Vintage Film (70s Grain)": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"1970s film photography aesthetic. Shot on Kodak Ektachrome 64T film stock. "
"Warm amber color cast, heavy film grain, slight lens softness. "
"Natural available light -- practicals, tungsten, daylight through windows. "
"Vintage clothing and environments accurate to the 1970s. "
"16:9 widescreen. Real photography, not illustration. "
"NEVER: digital look, sharp/clinical, modern objects, neon, anime. "
),
"primary": (
"1970s documentary photograph on Kodak film stock. Heavy visible film grain. "
"Warm amber and brown tones with faded blacks. Slight lens softness at edges. "
"Available light only -- practical lamps, sunlight, overhead fluorescent. "
"Period-accurate environments and wardrobe. "
"Style reference: Alan Pakula, Sidney Lumet cinematography. "
"Mood: paranoid, gritty, authentic. "
),
"secondary": (
"1970s educational filmstrip aesthetic. Vintage overhead projector look. "
"Faded colors, rounded corners, light leak effects. "
"Simple diagrams with hand-drawn labels on yellowed paper. "
),
"char_base": (
"1970s portrait photograph on Kodak film stock. Heavy grain, warm amber tones. "
"Front view and 3/4 view side by side. "
"Natural available light, shallow depth of field. "
"Period-accurate clothing and hairstyle. "
"Slight lens softness. Documentary portrait style. "
),
"grade": {"desat": 0.10, "teal_r": 5, "teal_g": -3, "teal_b": -10, "warm_r": 18, "warm_g": 8, "warm_b": -5, "contrast": 1.03, "vignette": 0.35, "grain": 12},
},
"Oil Painting / Classical": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Classical oil painting on canvas. Visible brushstrokes, rich impasto texture. "
"Rembrandt and Caravaggio chiaroscuro lighting -- dramatic single source. "
"Deep rich colors -- burnt sienna, raw umber, cadmium yellow, ultramarine blue. "
"Gallery-quality fine art, museum-worthy composition. "
"16:9 widescreen. Traditional oil painting medium. "
"NEVER: digital art, photorealistic, cartoon, anime, flat colors. "
),
"primary": (
"Classical oil painting on canvas. Rich impasto brushstrokes visible in texture. "
"Chiaroscuro lighting -- single dramatic light source, deep shadow. "
"Old master composition and color palette -- warm earth tones, deep blues. "
"Figures have weight and presence, draped in rich fabrics. "
"Style reference: Rembrandt, Caravaggio, Vermeer. "
"Mood: dramatic, timeless, gravitas. "
),
"secondary": (
"Technical illustration in old master drawing style. "
"Sepia ink on parchment paper. Leonardo da Vinci notebook aesthetic. "
"Cross-section diagrams with handwritten labels. Aged paper texture. "
),
"char_base": (
"Classical oil portrait painting. Rich brushwork, canvas texture visible. "
"Front view and 3/4 view side by side. "
"Chiaroscuro lighting -- dramatic single source. "
"Deep rich earth tone palette. Gallery-worthy composition. "
"Old master portrait style -- Rembrandt, Caravaggio influence. "
),
"grade": {"desat": 0.05, "teal_r": 0, "teal_g": -5, "teal_b": -8, "warm_r": 15, "warm_g": 8, "warm_b": -3, "contrast": 1.06, "vignette": 0.30, "grain": 2},
},
"Watercolor / Storybook": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Delicate watercolor painting on textured paper. Visible paper grain and water blooms. "
"Soft diffused edges, subtle color bleeding between shapes. "
"Pastel and muted color palette -- soft blues, warm pinks, sage greens, cream. "
"Gentle and contemplative mood. Children's book illustration quality. "
"16:9 widescreen. Traditional watercolor medium. "
"NEVER: photorealistic, harsh shadows, neon colors, anime, digital look. "
),
"primary": (
"Watercolor illustration on textured cold-pressed paper. "
"Visible paper grain, soft wet-on-wet color bleeds, delicate dry brush details. "
"Soft diffused natural lighting -- no harsh shadows. "
"Muted pastel palette with occasional deeper accent colors. "
"Style reference: Shaun Tan, Jon Klassen, Beatrix Potter. "
"Mood: gentle, contemplative, melancholic beauty. "
),
"secondary": (
"Watercolor diagram on cream paper. Soft hand-painted labels and arrows. "
"Botanical illustration precision meets watercolor softness. "
"Educational diagram with artistic beauty. Aged paper texture. "
),
"char_base": (
"Watercolor character illustration on textured paper. "
"Front view and 3/4 view side by side. "
"Soft edges, visible paper grain, subtle color bleeding. "
"Gentle muted palette. Delicate brushwork. "
"Children's book illustration quality. Cream paper background. "
),
"grade": {"desat": 0.0, "teal_r": 0, "teal_g": 2, "teal_b": 5, "warm_r": 5, "warm_g": 3, "warm_b": 0, "contrast": 1.02, "vignette": 0.10, "grain": 0},
},
"Clay / Stop Motion": {
"world_anchor": (
"PERSISTENT WORLD RULES: "
"Claymation stop-motion animation style. Characters and environments made of clay and plasticine. "
"Visible fingerprints and tool marks on surfaces. Miniature practical sets. "
"Warm studio lighting with soft shadows. Slightly textured, handmade quality. "
"16:9 widescreen. Laika Studios / Aardman quality. "
"NEVER: photorealistic, anime, flat 2D, digital smooth surfaces. "
),
"primary": (
"Claymation stop-motion scene. Characters sculpted from plasticine clay. "
"Miniature practical set with handcrafted props and environments. "
"Visible fingerprints and sculpting tool marks on all surfaces. "
"Warm studio lighting, soft shadows, shallow depth of field from macro lens. "
"Tilt-shift miniature effect. Coraline / Kubo quality. "
"Mood: tactile, handcrafted, charming but slightly eerie. "
),
"secondary": (
"Claymation diorama cutaway. Miniature cross-section model on turntable. "
"Clay and wire armature visible in educational explainer style. "
"Warm studio lighting, clean presentation. "
),
"char_base": (
"Claymation character design. Sculpted plasticine clay figure. "
"Front view and 3/4 view side by side on miniature turntable. "
"Visible fingerprints, handmade texture. Wire armature poseable joints. "
"Warm studio lighting. Macro lens shallow depth of field. "
"Laika Studios quality -- Coraline, Kubo aesthetic. "
),
"grade": {"desat": 0.0, "teal_r": 0, "teal_g": 2, "teal_b": 0, "warm_r": 10, "warm_g": 6, "warm_b": 0, "contrast": 1.04, "vignette": 0.15, "grain": 2},
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

    m = re.search(r'music:\s*"([^"]+)"', ptext)
    if m:
        p['m'] = m.group(1)

    m = re.search(r'vo:\s*"((?:[^"\\]|\\.)*)"', ptext)
    if m:
        p['vo'] = m.group(1)

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
    elif 'media' in t or t == 'media':
        return 'media'
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
        base_desc = desc.split(". Mannequin: ")[-1] if ". Mannequin: " in desc else desc
        views = {
            "front": f"CHARACTER REFERENCE -- FRONT VIEW. {base_desc} Light-toned smooth mannequin skin. Standing straight.",
            "three_quarter": f"CHARACTER REFERENCE -- 3/4 VIEW. {base_desc} Light-toned smooth mannequin skin. Slight turn.",
            "action": f"CHARACTER REFERENCE -- ACTION POSE. {base_desc} Light-toned smooth mannequin skin. In action.",
        }
        extracted[cid] = {
            "name": name,
            "alias": aliases,
            "desc": desc,
            "views": views,
        }
    return extracted


def _make_char_id(name):
    """Generate a short character ID from name. Project-agnostic."""
    name_lower = name.lower().strip()
    skip_words = {"the", "and", "of", "da", "de", "dos", "das", "del", "van", "von", "di"}
    words = re.sub(r'[^a-z0-9\s]', '', name_lower).split()
    for w in words:
        if w not in skip_words and len(w) > 2:
            return w[:8]
    return re.sub(r'[^a-z0-9]', '', name_lower)[:8] or "char"


def _extract_aliases(name, desc):
    """Generate detection aliases from character name and description."""
    aliases = []
    parts = re.split(r'[\s\(\)]+', name)
    for p in parts:
        p = p.strip()
        if len(p) > 2 and p.lower() not in {"the", "and"}:
            aliases.append(p)

    if "(" in name:
        before = name.split("(")[0].strip()
        inside = name.split("(")[1].rstrip(")")
        if before:
            aliases.append(before)
        for w in inside.split():
            if len(w) > 3:
                aliases.append(w)

    phrases = re.split(r'[,\.\;\-]+', desc)
    for phrase in phrases:
        phrase = phrase.strip().lower()
        words = phrase.split()
        if any(w in _CLOTHING_WORDS or w in _ROLE_WORDS for w in words) and 2 <= len(words) <= 6:
            aliases.append(phrase)

    desc_lower = re.sub(r'[^\w\s]', ' ', desc.lower())
    desc_words = desc_lower.split()
    for i, w in enumerate(desc_words):
        if w in _ROLE_WORDS or w in _CLOTHING_WORDS:
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
        if key not in seen and len(key) > 2:
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
    """Detect characters in prompt. Returns list of char IDs."""
    text = ((prompt or "") + " " + (vo or "")).lower()
    chars = get_active_characters()
    found = []
    for cid, c in chars.items():
        for alias in c["alias"]:
            if alias.lower() in text:
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


def gen_chat_section(client, section_name, panels_data, callback=None):
    """Generate panels in a section using chat for visual memory."""
    results = {}
    try:
        chat = client.chats.create(model=get_active_model())
        try:
            chat.send_message(
                f"You are generating a cinematic documentary storyboard. "
                f"Section: {section_name}. {get_world_anchor()} "
                f"Maintain absolute visual consistency across all images."
            )
        except:
            pass

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
                        contents2 = [pd["prompt"]]
                        resp2 = chat.send_message(contents2, config=get_config())
                        img2 = extract_image(resp2)
                        if img2:
                            out_path.write_bytes(img2)
                            results[pid] = True
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
