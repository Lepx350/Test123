"""
LAYER 13: CINEMATIC DIRECTOR AI
Storyboard Engine v10.4

Reads story beats from VO text and automatically determines:
- Camera angle & framing
- Lens choice (mm)
- Lighting mood & direction
- Composition rule
- Shot transition logic

Injects professional cinematography language into every panel prompt.
No two consecutive panels get the same camera setup.
Follows real film grammar: 180-degree rule, shot escalation, emotional pacing.

Drop this file alongside engine.py. Import and call inject_cinematography() in build_prompt().
"""

import re
from collections import deque

# ═══════════════════════════════════════════════════════════
# STORY BEAT DETECTION
# ═══════════════════════════════════════════════════════════

# Keywords that signal different story beats
_BEAT_PATTERNS = {
    "establishing": {
        "keywords": ["morning", "evening", "night", "dawn", "dusk", "city", "town",
                     "building", "exterior", "street", "arrive", "approach", "year",
                     "located", "situated", "neighborhood", "district"],
        "phrases": ["it was", "it is", "welcome to", "this is", "in the heart of",
                    "on the outskirts", "miles from", "kilometers from"],
    },
    "tension": {
        "keywords": ["nervous", "careful", "quiet", "slowly", "watching", "waiting",
                     "surveillance", "hidden", "secret", "risk", "danger", "alarm",
                     "security", "camera", "guard", "patrol", "suspect", "shadow",
                     "creep", "sneak", "whisper", "silence"],
        "phrases": ["no one noticed", "couldn't be seen", "heart pounding", "held breath",
                    "one wrong move", "if they were caught", "the clock was ticking"],
    },
    "action": {
        "keywords": ["run", "chase", "grab", "break", "smash", "drill", "cut", "dig",
                     "escape", "flee", "rush", "explode", "crash", "fight", "struggle",
                     "sprint", "burst", "shatter", "force", "rip", "tear", "haul"],
        "phrases": ["all at once", "in an instant", "everything changed", "no turning back",
                    "it was now or never"],
    },
    "revelation": {
        "keywords": ["discover", "realize", "reveal", "found", "truth", "actually",
                     "secret", "hidden", "uncover", "expose", "shock", "stunned",
                     "impossible", "unbelievable", "million", "billion", "worth"],
        "phrases": ["what they found", "no one knew", "the real story", "it turned out",
                    "the truth was", "for the first time", "they had no idea"],
    },
    "emotional": {
        "keywords": ["family", "wife", "husband", "child", "children", "mother", "father",
                     "friend", "betray", "trust", "love", "loss", "regret", "guilt",
                     "tears", "cry", "alone", "abandoned", "sacrifice", "promise",
                     "dream", "hope", "broken"],
        "phrases": ["never saw again", "for the last time", "all he wanted", "she never knew",
                    "the price they paid", "what it cost them"],
    },
    "aftermath": {
        "keywords": ["arrest", "prison", "sentence", "guilty", "verdict", "trial",
                     "convicted", "caught", "extradited", "testimony", "evidence",
                     "years later", "today", "remains", "legacy", "aftermath",
                     "consequence", "recovered", "returned"],
        "phrases": ["it was over", "they were caught", "justice was served", "to this day",
                    "no one ever found", "the money was never", "remains a mystery"],
    },
}


def detect_story_beat(vo_text: str, prompt_text: str = "") -> str:
    """Analyze VO and prompt text to determine the story beat.
    Returns one of: establishing, tension, action, revelation, emotional, aftermath.
    Falls back to 'tension' (default noir mood) if ambiguous."""
    text = ((vo_text or "") + " " + (prompt_text or "")).lower()
    if not text.strip():
        return "tension"

    scores = {}
    for beat, patterns in _BEAT_PATTERNS.items():
        score = 0
        for kw in patterns["keywords"]:
            if kw in text:
                score += 1
        for phrase in patterns["phrases"]:
            if phrase in text:
                score += 3  # Phrases are stronger signals
        scores[beat] = score

    if max(scores.values()) == 0:
        return "tension"  # Default noir mood

    return max(scores, key=scores.get)


# ═══════════════════════════════════════════════════════════
# CAMERA ANGLE SYSTEM
# ═══════════════════════════════════════════════════════════

_CAMERA_ANGLES = {
    "extreme_wide": {
        "prompt": "Extreme wide shot, full environment visible, character small in frame. ",
        "purpose": "establish scale, show isolation or grandeur",
        "beats": ["establishing", "aftermath"],
        "weight": 0.8,
    },
    "wide": {
        "prompt": "Wide shot, full body visible, environment dominant. ",
        "purpose": "establish location, show character in context",
        "beats": ["establishing", "action", "aftermath"],
        "weight": 1.0,
    },
    "medium_wide": {
        "prompt": "Medium wide shot, character from knees up, environment visible. ",
        "purpose": "walking shots, group dynamics",
        "beats": ["tension", "action", "emotional"],
        "weight": 0.9,
    },
    "medium": {
        "prompt": "Medium shot, character from waist up. ",
        "purpose": "conversation, standard coverage",
        "beats": ["tension", "emotional", "revelation", "aftermath"],
        "weight": 1.0,
    },
    "medium_closeup": {
        "prompt": "Medium close-up, character from chest up, face prominent. ",
        "purpose": "emotional reaction, dialogue emphasis",
        "beats": ["emotional", "revelation", "tension"],
        "weight": 0.9,
    },
    "closeup": {
        "prompt": "Close-up, character head and shoulders filling frame. ",
        "purpose": "emotion, intensity, confrontation",
        "beats": ["revelation", "emotional", "tension"],
        "weight": 0.85,
    },
    "extreme_closeup": {
        "prompt": "Extreme close-up on hands, object, or detail. ",
        "purpose": "critical detail, evidence, turning point",
        "beats": ["revelation", "tension", "action"],
        "weight": 0.6,
    },
    "overhead": {
        "prompt": "Overhead bird's-eye view, looking straight down. ",
        "purpose": "god's eye view, planning, aftermath",
        "beats": ["establishing", "revelation", "aftermath"],
        "weight": 0.5,
    },
    "low_angle": {
        "prompt": "Low angle shot, camera looking up at subject, imposing perspective. ",
        "purpose": "power, dominance, threat",
        "beats": ["tension", "action", "revelation"],
        "weight": 0.7,
    },
    "high_angle": {
        "prompt": "High angle shot, camera looking down at subject, diminishing perspective. ",
        "purpose": "vulnerability, surveillance, helplessness",
        "beats": ["emotional", "aftermath", "tension"],
        "weight": 0.6,
    },
    "dutch_angle": {
        "prompt": "Dutch angle, tilted camera, off-kilter framing. ",
        "purpose": "unease, disorientation, chaos",
        "beats": ["tension", "action"],
        "weight": 0.3,
    },
    "over_shoulder": {
        "prompt": "Over-the-shoulder shot, foreground character blurred, background subject in focus. ",
        "purpose": "conversation, confrontation, POV",
        "beats": ["tension", "emotional", "revelation"],
        "weight": 0.7,
    },
    "pov": {
        "prompt": "Point-of-view shot, camera sees what the character sees. ",
        "purpose": "immersion, discovery, surveillance",
        "beats": ["tension", "revelation", "action"],
        "weight": 0.5,
    },
}


# ═══════════════════════════════════════════════════════════
# LENS SYSTEM
# ═══════════════════════════════════════════════════════════

_LENSES = {
    "24mm": {
        "prompt": "24mm wide-angle lens, slight barrel distortion, expansive depth. ",
        "beats": ["establishing", "action"],
        "angles": ["extreme_wide", "wide", "low_angle"],
    },
    "35mm": {
        "prompt": "35mm lens, documentary feel, natural perspective. ",
        "beats": ["establishing", "tension", "aftermath"],
        "angles": ["wide", "medium_wide", "medium", "over_shoulder"],
    },
    "50mm": {
        "prompt": "50mm lens, human-eye perspective, neutral compression. ",
        "beats": ["tension", "emotional", "aftermath"],
        "angles": ["medium", "medium_closeup", "over_shoulder"],
    },
    "85mm": {
        "prompt": "85mm portrait lens, beautiful shallow depth of field, creamy bokeh. ",
        "beats": ["emotional", "revelation", "tension"],
        "angles": ["medium_closeup", "closeup", "medium"],
    },
    "135mm": {
        "prompt": "135mm telephoto, compressed background, isolation effect, surveillance feel. ",
        "beats": ["tension", "revelation"],
        "angles": ["closeup", "extreme_closeup", "medium_closeup"],
    },
}


# ═══════════════════════════════════════════════════════════
# LIGHTING SYSTEM
# ═══════════════════════════════════════════════════════════

_LIGHTING_MOODS = {
    "establishing": {
        "prompt": (
            "Establishing mood lighting: wide atmospheric illumination, "
            "distant practical lights visible (streetlamps, building windows), "
            "ambient city glow, long shadows. "
        ),
    },
    "tension": {
        "prompt": (
            "Noir tension lighting: single harsh key light from the side, "
            "deep pooling shadows obscuring half the frame, "
            "no fill light, darkness encroaching. "
        ),
    },
    "action": {
        "prompt": (
            "Kinetic action lighting: multiple competing light sources, "
            "sharp moving shadows, strobing effect from flashlights or sparks, "
            "high contrast, chaotic energy. "
        ),
    },
    "revelation": {
        "prompt": (
            "Revelation spotlight: single dramatic top-down light isolating the subject, "
            "everything else falls to deep shadow, "
            "spotlight effect, divine/interrogation feel. "
        ),
    },
    "emotional": {
        "prompt": (
            "Emotional Rembrandt lighting: soft key light from 45 degrees, "
            "gentle shadow triangle on far cheek, warm-to-cool color split, "
            "intimate, painterly quality. "
        ),
    },
    "aftermath": {
        "prompt": (
            "Aftermath flat lighting: diffused overcast daylight or harsh fluorescent, "
            "no drama in the light — the drama is in the content, "
            "clinical, institutional, desaturated. "
        ),
    },
}


# ═══════════════════════════════════════════════════════════
# COMPOSITION SYSTEM
# ═══════════════════════════════════════════════════════════

_COMPOSITIONS = {
    "rule_of_thirds": {
        "prompt": "Composed on rule of thirds — subject placed at intersection point, space in direction of gaze. ",
        "beats": ["tension", "emotional", "aftermath"],
        "weight": 1.0,
    },
    "center_frame": {
        "prompt": "Center-framed composition — subject dead center, symmetrical power, confrontational. ",
        "beats": ["revelation", "action", "tension"],
        "weight": 0.7,
    },
    "leading_lines": {
        "prompt": "Leading lines composition — architectural lines or road/tunnel converging toward subject. ",
        "beats": ["establishing", "tension", "action"],
        "weight": 0.8,
    },
    "frame_within_frame": {
        "prompt": "Frame-within-frame composition — subject seen through doorway, window, mirror, or archway. ",
        "beats": ["tension", "revelation", "emotional"],
        "weight": 0.6,
    },
    "negative_space": {
        "prompt": "Negative space composition — subject small in frame, vast emptiness around them, isolation. ",
        "beats": ["emotional", "aftermath", "establishing"],
        "weight": 0.5,
    },
    "diagonal": {
        "prompt": "Dynamic diagonal composition — key elements arranged along a strong diagonal line, energy and movement. ",
        "beats": ["action", "tension"],
        "weight": 0.6,
    },
    "foreground_depth": {
        "prompt": "Depth composition — blurred foreground object framing sharp subject in background, layered depth. ",
        "beats": ["tension", "revelation", "emotional"],
        "weight": 0.7,
    },
}


# ═══════════════════════════════════════════════════════════
# SHOT VARIETY TRACKER
# ═══════════════════════════════════════════════════════════

class DirectorMemory:
    """Tracks recent camera decisions to ensure variety."""

    def __init__(self):
        self.recent_angles = deque(maxlen=4)
        self.recent_lenses = deque(maxlen=3)
        self.recent_compositions = deque(maxlen=3)
        self.section_angles = {}
        self.panel_count = 0

    def reset_section(self, section_name: str):
        """Reset for new section (allows re-establishing)."""
        self.recent_angles.clear()
        self.recent_lenses.clear()
        self.recent_compositions.clear()
        self.section_angles[section_name] = []
        self.panel_count = 0

    def record(self, angle: str, lens: str, composition: str, section: str = ""):
        """Record a camera decision."""
        self.recent_angles.append(angle)
        self.recent_lenses.append(lens)
        self.recent_compositions.append(composition)
        self.panel_count += 1
        if section and section in self.section_angles:
            self.section_angles[section].append(angle)

    def is_allowed(self, angle: str) -> bool:
        """Check if an angle is allowed (not too recently used)."""
        if not self.recent_angles:
            return True
        if self.recent_angles[-1] == angle:
            return False
        if self.recent_angles.count(angle) >= 2:
            return False
        return True

    def is_lens_allowed(self, lens: str) -> bool:
        """Avoid same lens 3x in a row."""
        if len(self.recent_lenses) < 2:
            return True
        return not (self.recent_lenses[-1] == lens and
                    len(self.recent_lenses) > 1 and
                    self.recent_lenses[-2] == lens)


# Global director memory instance
_director = DirectorMemory()


# ═══════════════════════════════════════════════════════════
# SHOT ESCALATION LOGIC
# ═══════════════════════════════════════════════════════════

_ESCALATION_ORDER = [
    "extreme_wide", "wide", "medium_wide", "medium",
    "medium_closeup", "closeup", "extreme_closeup"
]


def _get_escalation_preference(beat: str, panel_in_section: int, total_in_section: int) -> str:
    """Determine if we should be escalating (tighter) or de-escalating (wider)."""
    if panel_in_section <= 2:
        return "de-escalate"
    if total_in_section > 0:
        progress = panel_in_section / max(total_in_section, 1)
    else:
        progress = 0.5

    if beat in ("action", "revelation", "tension"):
        if progress < 0.7:
            return "escalate"
        else:
            return "neutral"
    elif beat in ("aftermath", "establishing"):
        return "de-escalate"
    elif beat == "emotional":
        if progress < 0.5:
            return "escalate"
        else:
            return "de-escalate"
    return "neutral"


# ═══════════════════════════════════════════════════════════
# MAIN CINEMATOGRAPHY INJECTION
# ═══════════════════════════════════════════════════════════

def select_camera_angle(beat: str, panel_index: int = 0,
                        section_total: int = 20) -> str:
    """Select the best camera angle for this beat, respecting variety rules."""
    import random

    escalation = _get_escalation_preference(beat, panel_index, section_total)

    candidates = []
    for angle_name, angle_data in _CAMERA_ANGLES.items():
        if beat in angle_data["beats"] and _director.is_allowed(angle_name):
            weight = angle_data["weight"]
            if escalation == "escalate":
                idx = _ESCALATION_ORDER.index(angle_name) if angle_name in _ESCALATION_ORDER else 3
                weight *= (idx + 1) / len(_ESCALATION_ORDER)
            elif escalation == "de-escalate":
                idx = _ESCALATION_ORDER.index(angle_name) if angle_name in _ESCALATION_ORDER else 3
                weight *= (len(_ESCALATION_ORDER) - idx) / len(_ESCALATION_ORDER)
            candidates.append((angle_name, weight))

    if not candidates:
        candidates = [(a, d["weight"]) for a, d in _CAMERA_ANGLES.items()
                      if _director.is_allowed(a)]

    if not candidates:
        return "medium"

    total_weight = sum(w for _, w in candidates)
    r = random.random() * total_weight
    cumulative = 0
    for angle_name, weight in candidates:
        cumulative += weight
        if r <= cumulative:
            return angle_name
    return candidates[0][0]


def select_lens(beat: str, angle: str) -> str:
    """Select the best lens for this beat + angle combination."""
    candidates = []
    for lens_name, lens_data in _LENSES.items():
        if beat in lens_data["beats"] and angle in lens_data["angles"]:
            if _director.is_lens_allowed(lens_name):
                candidates.append(lens_name)

    if not candidates:
        candidates = [ln for ln, ld in _LENSES.items()
                      if angle in ld["angles"] and _director.is_lens_allowed(ln)]

    if not candidates:
        return "50mm"

    import random
    return random.choice(candidates)


def select_composition(beat: str) -> str:
    """Select composition rule for this beat, avoiding repeats."""
    import random
    candidates = []
    for comp_name, comp_data in _COMPOSITIONS.items():
        if beat in comp_data["beats"] and comp_name not in _director.recent_compositions:
            candidates.append((comp_name, comp_data["weight"]))

    if not candidates:
        candidates = [(c, d["weight"]) for c, d in _COMPOSITIONS.items()
                      if c not in _director.recent_compositions]

    if not candidates:
        return "rule_of_thirds"

    total_weight = sum(w for _, w in candidates)
    r = random.random() * total_weight
    cumulative = 0
    for comp_name, weight in candidates:
        cumulative += weight
        if r <= cumulative:
            return comp_name
    return candidates[0][0]


def inject_cinematography(vo_text: str, prompt_text: str = "",
                          section_name: str = "",
                          panel_index: int = 0,
                          section_total: int = 20,
                          is_first_in_section: bool = False) -> str:
    """MAIN ENTRY POINT: Generate cinematography injection for a panel.

    Args:
        vo_text: The voiceover text for this panel
        prompt_text: The original gemini prompt for this panel
        section_name: Current section name
        panel_index: Panel's position within its section (0-based)
        section_total: Total panels in this section
        is_first_in_section: True if this is the first panel in a new section

    Returns:
        String to prepend to the panel prompt with camera, lens, lighting, composition.
    """
    if is_first_in_section:
        _director.reset_section(section_name)

    beat = detect_story_beat(vo_text, prompt_text)
    angle = select_camera_angle(beat, panel_index, section_total)
    lens = select_lens(beat, angle)
    composition = select_composition(beat)
    _director.record(angle, lens, composition, section_name)

    angle_prompt = _CAMERA_ANGLES[angle]["prompt"]
    lens_prompt = _LENSES[lens]["prompt"]
    lighting_prompt = _LIGHTING_MOODS.get(beat, _LIGHTING_MOODS["tension"])["prompt"]
    comp_prompt = _COMPOSITIONS[composition]["prompt"]

    injection = (
        f"CINEMATOGRAPHY DIRECTION: "
        f"{angle_prompt}"
        f"{lens_prompt}"
        f"{lighting_prompt}"
        f"{comp_prompt}"
    )

    return injection


def get_beat_for_logging(vo_text: str, prompt_text: str = "") -> str:
    """Get the detected beat name for logging/debugging."""
    return detect_story_beat(vo_text, prompt_text)


if __name__ == "__main__":
    test_panels = [
        ("It's Monday morning, August 8th, 2005. Fortaleza, Brazil.", "Wide shot of bank exterior at dawn"),
        ("Inside the vault, 3.5 tons of cash sit undisturbed.", "Vault interior with stacked cash"),
        ("The gang had been digging for three months straight.", "Men digging underground tunnel"),
        ("At exactly 2 AM, they broke through the vault floor.", "Concrete floor cracking open from below"),
        ("What police found shocked the entire nation.", "Empty vault with hole in floor"),
    ]

    print("=" * 70)
    print("LAYER 13: CINEMATIC DIRECTOR AI — Test Run")
    print("=" * 70)

    for i, (vo, prompt) in enumerate(test_panels):
        result = inject_cinematography(
            vo, prompt, section_name="S1",
            panel_index=i, section_total=len(test_panels),
            is_first_in_section=(i == 0)
        )
        beat = get_beat_for_logging(vo, prompt)
        print(f"\n--- Panel {i+1} ---")
        print(f"VO: \"{vo[:60]}\"")
        print(f"Beat: {beat.upper()}")
        print(f"Director: {result[:120]}...")
