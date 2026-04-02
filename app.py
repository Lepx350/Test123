"""
Storyboard Visual Engine v7 — Web Edition
Deploy to Railway.app or run locally.
Phone: open browser → use from anywhere.
"""
import os, json, time, threading, shutil, base64
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, send_file, send_from_directory
from engine import (
    STYLE_PRESETS, CHARACTERS, ENVIRONMENTS, MASTER_SHOT_DETAILS,
    active_preset, image_settings, RESOLUTION_MAP, AR_OPTIONS, MODEL_OPTIONS,
    parse_storyboard, get_asset_type, get_image_prompt, get_section,
    detect_characters, detect_environment, count_words,
    get_world_anchor, get_primary_style, get_secondary_style,
    get_char_base, get_grade_params, get_char_view_prompt, get_char_sheet_prompt, get_env_prompt,
    get_master_shot_prompt, get_style_anchor_prompt, score_consistency, build_adaptive_prompt, build_prompt,
    get_config, gen_single, gen_chat_section, extract_image,
    post_process, VisualMemoryBank, adaptive_delay,
    load_config, save_config,
    load_dynamic_characters, get_active_characters,
    load_dynamic_environments, get_active_environments, get_active_master_shots,
)
import engine

app = Flask(__name__)

# ── STATE ──
state = {
    "panels": [], "noir": [], "fern": [], "gen": [],
    "char_map": {}, "env_map": {}, "used_chars": [], "used_envs": [],
    "warnings": [], "output_dir": None, "memory_bank": None,
    "running": False, "stop": False, "log": [], "progress": 0, "total": 0,
    "storyboard_text": "",
    "current_section": "", "section_progress": {}, "current_panel": "",
}

def log(msg, tag="info"):
    state["log"].append({"msg": msg, "tag": tag, "ts": time.time()})

def prog(done, total):
    state["progress"] = done
    state["total"] = total

# ── ROUTES ──
@app.route("/")
def index():
    cfg = load_config()
    # API key priority: config file > env var
    saved_key = cfg.get("api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    return render_template("index.html",
        presets=list(STYLE_PRESETS.keys()),
        resolutions=list(RESOLUTION_MAP.keys()),
        ar_options=AR_OPTIONS,
        model_options=list(MODEL_OPTIONS.keys()),
        saved_key=saved_key,
        saved_style=cfg.get("style", list(STYLE_PRESETS.keys())[0]),
        saved_res=cfg.get("resolution", "2K (recommended)"),
        saved_ar=cfg.get("aspect_ratio", "16:9"),
        saved_model=cfg.get("model", "Nano Banana Pro (Best)"),
    )

@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("storyboard")
    if not f:
        return jsonify(error="No file"), 400

    # Save storyboard
    upload_dir = Path("workspace")
    upload_dir.mkdir(exist_ok=True)
    path = upload_dir / f.filename
    f.save(str(path))

    text = path.read_text(encoding="utf-8")
    panels = parse_storyboard(text)
    if not panels:
        return jsonify(error="No panels found"), 400

    # Auto-extract characters from storyboard
    load_dynamic_characters(text)

    # Auto-extract environments from storyboard (or auto-detect from panels)
    load_dynamic_environments(text, panels)

    # Setup output dirs
    out = upload_dir / "generated_images"
    for d in ["characters",
              "environments", "master_shots", "scenes", "post_processed", "final", "style_anchor"]:
        (out / d).mkdir(parents=True, exist_ok=True)

    state["panels"] = panels
    state["storyboard_text"] = text
    state["output_dir"] = out
    state["memory_bank"] = VisualMemoryBank(out)

    # Generate in SCRIPT ORDER — no noir/fern grouping
    noir = [p for p in panels if get_asset_type(p) == 'noir' and get_image_prompt(p)]
    fern = [p for p in panels if get_asset_type(p) == 'fern' and get_image_prompt(p)]
    gen = [p for p in panels if get_asset_type(p) in ('noir', 'fern') and get_image_prompt(p)]
    state["noir"] = noir  # kept for stats only
    state["fern"] = fern  # kept for stats only
    state["gen"] = gen    # script order — this is what gets generated

    warnings = []
    char_map = {}; env_map = {}

    for p in gen:
        pid = p['id']
        prompt = get_image_prompt(p)
        vo = p.get('vo', '')
        chars = detect_characters(prompt, vo)
        char_map[pid] = chars
        env_map[pid] = detect_environment(prompt, vo)
        if len(chars) > 1:
            warnings.append(f"{pid}: {len(chars)} chars, using @{chars[0]}")
        if count_words(prompt) > 60:
            warnings.append(f"{pid}: {count_words(prompt)} words (max 60)")
        cold = p.get('co', p.get('coldOpen', 0))
        if cold and get_asset_type(p) != 'noir':
            warnings.append(f"{pid}: Cold open must be Noir")

    state["char_map"] = char_map
    state["env_map"] = env_map
    state["used_chars"] = list(set(c for cs in char_map.values() for c in cs))
    state["used_envs"] = list(set(e for e in env_map.values() if e))
    state["warnings"] = warnings
    state["log"] = []

    # Build sections
    sections = []
    sec_dict = {}
    for p in gen:
        sec = get_section(p)
        if sec not in sec_dict:
            sec_dict[sec] = []
            sections.append(sec)
        sec_dict[sec].append(p)

    # Count done per section
    sec_info = []
    for sec in sections:
        panels_in = sec_dict[sec]
        done = sum(1 for p in panels_in if (out / "scenes" / f"{p.get('f', p['id'])}.png").exists())
        sec_info.append({"name": sec, "total": len(panels_in), "done": done,
                         "noir": sum(1 for p in panels_in if get_asset_type(p)=='noir'),
                         "fern": sum(1 for p in panels_in if get_asset_type(p)=='fern'),
                         })

    return jsonify(
        total=len(panels), noir=len(noir), fern=len(fern),
        chars=len(state["used_chars"]), envs=len(state["used_envs"]),
        gen_count=len(gen), warnings=warnings, sections=sec_info,
    )

@app.route("/api/settings", methods=["POST"])
def settings():
    data = request.json
    if data.get("api_key"):
        save_config({"api_key": data["api_key"]})
    if data.get("style"):
        name = data["style"]
        if name in STYLE_PRESETS:
            engine.active_preset = STYLE_PRESETS[name]
        save_config({"style": name})
    if data.get("resolution"):
        engine.image_settings["resolution"] = data["resolution"]
        save_config({"resolution": data["resolution"]})
    if data.get("aspect_ratio"):
        engine.image_settings["aspect_ratio"] = data["aspect_ratio"]
        save_config({"aspect_ratio": data["aspect_ratio"]})
    if data.get("model"):
        model_label = data["model"]
        if model_label in MODEL_OPTIONS:
            engine.image_settings["model"] = MODEL_OPTIONS[model_label]
        save_config({"model": model_label})
    return jsonify(ok=True)

@app.route("/api/run/<step>", methods=["POST"])
def run_step(step):
    # Auto-reset stale running state
    if state["running"]:
        t = state.get("_thread")
        if t is None or not t.is_alive():
            state["running"] = False
            state["stop"] = False
        else:
            return jsonify(error="Already running"), 409
    data = request.json or {}
    key = data.get("api_key") or load_config().get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return jsonify(error="No API key"), 400
    save_config({"api_key": key})

    state["running"] = True
    state["stop"] = False
    state["log"] = []

    if step == "characters":
        t = threading.Thread(target=run_characters, args=(key,), daemon=True)
    elif step == "environments" or step == "master_shots":
        t = threading.Thread(target=run_environments, args=(key,), daemon=True)
    elif step == "scenes":
        sec = data.get("section", "__ALL__")
        t = threading.Thread(target=run_scenes, args=(key, sec), daemon=True)
    elif step == "color_grade":
        t = threading.Thread(target=run_color_grade, daemon=True)
    elif step == "export":
        t = threading.Thread(target=run_export, daemon=True)
    elif step == "full_pipeline":
        t = threading.Thread(target=run_full_pipeline, args=(key,), daemon=True)
    else:
        state["running"] = False
        return jsonify(error="Unknown step"), 400

    state["_thread"] = t
    t.start()
    return jsonify(ok=True)

@app.route("/api/stop", methods=["POST"])
def stop():
    state["stop"] = True
    return jsonify(ok=True)

@app.route("/api/delete_panel", methods=["POST"])
def delete_panel():
    """Delete a single panel image so it can be regenerated."""
    data = request.json or {}
    panel_id = data.get("panel_id")
    if not panel_id or not state["output_dir"]:
        return jsonify(error="No panel ID or no storyboard loaded"), 400

    out = state["output_dir"]
    deleted = []

    # Find and delete matching files in scenes/ and final/
    for folder in ["scenes", "final", "post_processed"]:
        d = out / folder
        if d.exists():
            for f in d.glob(f"*{panel_id}*"):
                f.unlink()
                deleted.append(str(f.name))

    if deleted:
        return jsonify(ok=True, deleted=deleted)
    return jsonify(ok=True, deleted=[], msg="No files found")

@app.route("/api/panels")
def list_panels():
    """Return all panels with metadata and done status."""
    if not state["output_dir"] or not state["panels"]:
        return jsonify(panels=[])
    out = state["output_dir"]
    gen = state.get("gen", [])
    result = []
    for p in gen:
        pid = p.get("id", "")
        fname = f"{p.get('f', pid)}.png"
        done = any((out / d / fname).exists() for d in ["final", "post_processed", "scenes"])
        chars = state["char_map"].get(pid, [])
        active_chars = get_active_characters()
        char_names = [active_chars.get(c, {}).get("name", c) for c in chars]
        result.append({
            "id": pid,
            "type": get_asset_type(p),
            "section": get_section(p),
            "vo": p.get("vo", "")[:120],
            "prompt": get_image_prompt(p)[:100],
            "chars": char_names,
            "env": state["env_map"].get(pid, ""),
            "done": done,
        })
    return jsonify(panels=result)

@app.route("/api/generate_one", methods=["POST"])
def generate_one():
    """Generate a single panel image with 12-layer consistency. Synchronous."""
    if state.get("running"):
        return jsonify(error="Pipeline running. Stop it first or wait."), 409
    data = request.json or {}
    panel_id = data.get("panel_id")
    if not panel_id:
        return jsonify(error="No panel_id"), 400
    if not state["output_dir"] or not state["panels"]:
        return jsonify(error="No storyboard loaded"), 400

    key = data.get("api_key") or load_config().get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return jsonify(error="No API key"), 400

    # Find panel
    gen = state.get("gen", [])
    panel = None
    for p in gen:
        if p.get("id") == panel_id:
            panel = p; break
    if not panel:
        return jsonify(error=f"Panel {panel_id} not found"), 404

    out = state["output_dir"]
    fname = f"{panel.get('f', panel_id)}.png"
    out_path = out / "scenes" / fname

    # Delete existing if regenerating
    for folder in ["scenes", "final", "post_processed"]:
        f = out / folder / fname
        if f.exists(): f.unlink()

    # ── LAYER 8: Gather ALL character refs ──
    pid = panel_id
    all_chars = state["char_map"].get(pid, [])
    env_id = state["env_map"].get(pid)
    asset = get_asset_type(panel)
    primary_char = all_chars[0] if all_chars else None

    refs = []
    if asset != 'fern':
        for cid in all_chars:
            sheet = out / "characters" / f"@{cid}.png"
            if sheet.exists() and str(sheet) not in refs:
                refs.append(str(sheet))
        if len(refs) > 3: refs = refs[:3]  # cap char refs at 3

    # ── LAYER 9: Style anchor ref ──
    style_anchor = out / "style_anchor" / "style_key.png"
    if style_anchor.exists() and len(refs) < 5:
        refs.append(str(style_anchor))

    # Environment ref
    if env_id and asset != 'fern' and len(refs) < 6:
        master = out / "master_shots" / f"{env_id}_master.png"
        basic = out / "environments" / f"{env_id}.png"
        if master.exists(): refs.append(str(master))
        elif basic.exists(): refs.append(str(basic))

    # ── LAYER 10: Section bridge ref ──
    mb = state.get("memory_bank")
    if mb and len(refs) < 6:
        section_order = list(dict.fromkeys(get_section(p) for p in gen))
        bridge = mb.get_previous_section_bridge(get_section(panel), section_order)
        if bridge and bridge not in refs:
            refs.append(bridge)

    # Build prompt with ALL characters (Layer 8) + cinematography (Layer 13)
    sec_name = get_section(panel)
    sec_panels = [p for p in gen if get_section(p) == sec_name]
    sec_total = len(sec_panels)
    p_idx = next((i for i, p in enumerate(sec_panels) if p.get("id") == panel_id), 0)
    prompt = build_prompt(
        panel, primary_char, env_id, all_chars=all_chars,
        section_name=sec_name, panel_index=p_idx,
        section_total=sec_total, is_first_in_section=(p_idx == 0)
    )

    try:
        client = get_client(key)
        img = gen_single(client, prompt, refs)
        if not img:
            return jsonify(error="No image returned from API"), 500
        out_path.write_bytes(img)

        # ── LAYER 11: Consistency scoring ──
        score = 100
        issues = ""
        char_refs_for_score = [str(out / "characters" / f"@{c}.png") for c in all_chars
                               if (out / "characters" / f"@{c}.png").exists()]
        if char_refs_for_score and asset != 'fern':
            score, issues = score_consistency(client, str(out_path), char_refs_for_score, pid)

        # ── LAYER 12: Adaptive retry if low score ──
        if score < 60 and char_refs_for_score:
            adaptive_prompt = build_adaptive_prompt(prompt, score, issues, attempt=1)
            retry_img = gen_single(client, adaptive_prompt, refs)
            if retry_img:
                out_path.write_bytes(retry_img)
                score2, issues2 = score_consistency(client, str(out_path), char_refs_for_score, pid)
                if score2 > score:
                    score, issues = score2, issues2

        # Update memory bank
        if mb:
            if primary_char: mb.update_char(primary_char, str(out_path))
            if env_id: mb.update_env(env_id, str(out_path))
            mb.update_section(get_section(panel), str(out_path))

        return jsonify(ok=True, panel_id=panel_id, size=len(img),
                      consistency_score=score, issues=issues)
    except Exception as e:
        return jsonify(error=str(e)[:200]), 500

@app.route("/api/stream")
def stream():
    """SSE endpoint for real-time log + progress + section tracking."""
    def gen():
        idx = 0
        while True:
            while idx < len(state["log"]):
                entry = state["log"][idx]
                yield f"data: {json.dumps({'type':'log','msg':entry['msg'],'tag':entry['tag']})}\n\n"
                idx += 1
            yield f"data: {json.dumps({'type':'progress','done':state['progress'],'total':state['total'],'running':state['running'],'current_section':state.get('current_section',''),'section_progress':state.get('section_progress',{}),'current_panel':state.get('current_panel','')})}\n\n"
            time.sleep(0.5)
    return Response(gen(), mimetype="text/event-stream")

@app.route("/api/images/<path:filename>")
def serve_image(filename):
    if state["output_dir"]:
        return send_from_directory(str(state["output_dir"]), filename)
    return "", 404

@app.route("/api/export_html")
def serve_export():
    path = Path("workspace/storyboard_visual.html")
    if path.exists():
        return send_file(str(path), as_attachment=True, download_name="storyboard_visual.html")
    return "Not exported yet", 404

@app.route("/api/preview/<panel_id>")
def preview_panel(panel_id):
    """Serve generated panel image for inline preview."""
    if not state["output_dir"]:
        return "No project loaded", 404
    out = state["output_dir"]
    for p in state.get("panels", []):
        if p.get("id") == panel_id:
            fname = f"{p.get('f', panel_id)}.png"
            for d in ["final", "post_processed", "scenes"]:
                path = out / d / fname
                if path.exists():
                    return send_file(str(path), mimetype="image/png")
    return "Not found", 404

@app.route("/api/panel_status")
def panel_status():
    """Return generation status for all panels."""
    if not state["output_dir"]:
        return jsonify(panels={})
    out = state["output_dir"]
    status = {}
    for p in state.get("panels", []):
        pid = p.get("id", "")
        fname = f"{p.get('f', pid)}.png"
        done = any((out / d / fname).exists() for d in ["final", "post_processed", "scenes"])
        status[pid] = {"done": done, "type": get_asset_type(p)}
    return jsonify(panels=status)

@app.route("/api/pipeline_status")
def pipeline_status():
    """Scan disk and return what's been generated at each pipeline stage."""
    if not state["output_dir"]:
        return jsonify(chars=[], envs=[], masters=[], scenes_done=0, scenes_total=0, graded=0)
    out = state["output_dir"]

    # Characters
    chars_done = []
    for cid in state.get("used_chars", []):
        sheet = out / "characters" / f"@{cid}.png"
        active_chars = get_active_characters()
        name = active_chars.get(cid, {}).get("name", cid)
        chars_done.append({
            "id": cid, "name": name,
            "done": sheet.exists(),
        })

    # Environments + Masters
    envs_done = []
    for eid in state.get("used_envs", []):
        env_path = out / "environments" / f"{eid}.png"
        master_path = out / "master_shots" / f"{eid}_master.png"
        envs_done.append({
            "id": eid, "name": get_active_environments().get(eid, {}).get("name", eid),
            "env": env_path.exists(),
            "master": master_path.exists(),
        })

    # Scenes
    gen = state.get("gen", [])
    scenes_done = sum(1 for p in gen if any(
        (out / d / f"{p.get('f', p['id'])}.png").exists()
        for d in ["final", "post_processed", "scenes"]
    ))

    # Graded
    graded = len(list((out / "post_processed").glob("*.png"))) if (out / "post_processed").exists() else 0

    # Style anchor (Layer 9)
    style_anchor = (out / "style_anchor" / "style_key.png").exists()

    return jsonify(
        chars=chars_done, envs=envs_done,
        scenes_done=scenes_done, scenes_total=len(gen), graded=graded,
        style_anchor=style_anchor,
    )

@app.route("/api/gen_style_anchor", methods=["POST"])
def gen_style_anchor_endpoint():
    """Generate the style anchor image (Layer 9)."""
    if not state["output_dir"]:
        return jsonify(error="No storyboard loaded"), 400
    data = request.json or {}
    key = data.get("api_key") or load_config().get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return jsonify(error="No API key"), 400
    out = state["output_dir"]
    style_path = out / "style_anchor" / "style_key.png"
    try:
        client = get_client(key)
        img = gen_single(client, get_style_anchor_prompt())
        if img:
            style_path.write_bytes(img)
            return jsonify(ok=True, size=len(img))
        return jsonify(error="No image returned"), 500
    except Exception as e:
        return jsonify(error=str(e)[:200]), 500

@app.route("/api/redo_ref", methods=["POST"])
def redo_ref():
    """Delete and regenerate a single reference image (character, env, or master)."""
    if not state["output_dir"]:
        return jsonify(error="No storyboard loaded"), 400
    data = request.json or {}
    ref_type = data.get("ref_type")
    ref_id = data.get("ref_id")
    key = data.get("api_key") or load_config().get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return jsonify(error="No API key"), 400
    if not ref_type or not ref_id:
        return jsonify(error="Missing ref_type or ref_id"), 400

    out = state["output_dir"]
    try:
        client = get_client(key)
        if ref_type == "char":
            p = out / "characters" / f"@{ref_id}.png"
            if p.exists(): p.unlink()
            img = gen_single(client, get_char_sheet_prompt(ref_id))
            if img: p.write_bytes(img); return jsonify(ok=True)
        elif ref_type == "env":
            p = out / "environments" / f"{ref_id}.png"
            if p.exists(): p.unlink()
            img = gen_single(client, get_env_prompt(ref_id))
            if img: p.write_bytes(img); return jsonify(ok=True)
        elif ref_type == "master":
            p = out / "master_shots" / f"{ref_id}_master.png"
            if p.exists(): p.unlink()
            env_ref = out / "environments" / f"{ref_id}.png"
            refs = [str(env_ref)] if env_ref.exists() else []
            prompt = get_master_shot_prompt(ref_id)
            if prompt:
                img = gen_single(client, prompt, refs)
                if img: p.write_bytes(img); return jsonify(ok=True)
        elif ref_type == "style_anchor":
            p = out / "style_anchor" / "style_key.png"
            if p.exists(): p.unlink()
            img = gen_single(client, get_style_anchor_prompt())
            if img: p.write_bytes(img); return jsonify(ok=True)
        return jsonify(error="No image returned"), 500
    except Exception as e:
        return jsonify(error=str(e)[:200]), 500

@app.route("/api/edit_ref", methods=["POST"])
def edit_ref():
    """Regenerate a ref image with a custom prompt. Style prefix auto-injected."""
    if not state["output_dir"]:
        return jsonify(error="No storyboard loaded"), 400
    data = request.json or {}
    ref_type = data.get("ref_type")
    ref_id = data.get("ref_id")
    custom_prompt = data.get("custom_prompt", "")
    key = data.get("api_key") or load_config().get("api_key") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return jsonify(error="No API key"), 400
    if not ref_type or not ref_id or not custom_prompt:
        return jsonify(error="Missing ref_type, ref_id, or custom_prompt"), 400

    out = state["output_dir"]

    # Auto-inject style based on ref type
    if ref_type == "char":
        styled_prompt = get_char_base() + custom_prompt
        p = out / "characters" / f"@{ref_id}.png"
    elif ref_type == "env":
        styled_prompt = get_world_anchor() + get_primary_style() + custom_prompt
        p = out / "environments" / f"{ref_id}.png"
    elif ref_type == "master":
        styled_prompt = get_world_anchor() + get_primary_style() + custom_prompt
        p = out / "master_shots" / f"{ref_id}_master.png"
    elif ref_type == "style_anchor":
        styled_prompt = get_world_anchor() + get_primary_style() + custom_prompt
        p = out / "style_anchor" / "style_key.png"
    else:
        return jsonify(error=f"Unknown ref type: {ref_type}"), 400

    try:
        if p.exists(): p.unlink()
        client = get_client(key)
        img = gen_single(client, styled_prompt)
        if img:
            p.write_bytes(img)
            return jsonify(ok=True, size=len(img))
        return jsonify(error="No image returned"), 500
    except Exception as e:
        return jsonify(error=str(e)[:200]), 500

@app.route("/api/ref/<ref_type>/<ref_name>")
def serve_ref(ref_type, ref_name):
    """Serve character/env/master/style reference images."""
    if not state["output_dir"]:
        return "No project", 404
    out = state["output_dir"]
    if ref_type == "char" or ref_type == "char_front" or ref_type == "char_tq" or ref_type == "char_action":
        p = out / "characters" / f"@{ref_name}.png"
    elif ref_type == "style_anchor":
        p = out / "style_anchor" / f"{ref_name}.png"
    elif ref_type == "env":
        p = out / "environments" / f"{ref_name}.png"
    elif ref_type == "master":
        p = out / "master_shots" / f"{ref_name}_master.png"
    else:
        return "Unknown type", 404
    if p.exists():
        return send_file(str(p), mimetype="image/png")
    return "Not found", 404

# ── GENERATION WORKERS ──
def get_client(key):
    from google import genai
    
    # Vertex AI Express Mode — uses $300 free credits
    # vertexai=True + api_key, NO project, NO location
    # Routes to global express endpoint, credits apply
    return genai.Client(
        vertexai=True,
        api_key=key,
    )

def run_characters(key):
    try:
        if not state["output_dir"]:
            log("ERROR: No storyboard uploaded", "fail"); return
        client = get_client(key)
        out = state["output_dir"]
        chars = sorted(state["used_chars"])
        total = len(chars)
        done = 0
        log(f"STEP 1: CHARACTER SHEETS ({total} characters)", "head")

        for cid in chars:
            if state["stop"]: break
            done += 1; prog(done, total)
            p = out / "characters" / f"@{cid}.png"
            if p.exists():
                log(f"[SKIP] @{cid}")
                continue
            log(f"[GEN] @{cid} sheet...")
            try:
                img = gen_single(client, get_char_sheet_prompt(cid))
                if img: p.write_bytes(img); log(f"OK → @{cid}", "ok")
                else: log(f"WARN @{cid}", "warn")
            except Exception as e:
                log(f"FAIL: {str(e)[:80]}", "fail")
            adaptive_delay.wait()
        log("Step 1 done!", "ok")
    except Exception as e:
        log(f"PIPELINE ERROR: {str(e)[:120]}", "fail")
    finally:
        state["running"] = False

def run_environments(key):
    """Combined: generate env refs + master shots for each environment."""
    try:
        client = get_client(key)
        out = state["output_dir"]
        envs = sorted(state["used_envs"])
        total = len(envs) * 2  # env + master per location
        done = 0
        log(f"STEP 2: ENVIRONMENTS + MASTERS ({len(envs)} locations)", "head")
        for eid in envs:
            if state["stop"]: break
            # Env ref
            done += 1; prog(done, total)
            p = out / "environments" / f"{eid}.png"
            if p.exists():
                log(f"[SKIP] {eid}")
            else:
                log(f"[GEN] {eid}...")
                try:
                    img = gen_single(client, get_env_prompt(eid))
                    if img: p.write_bytes(img); log(f"OK → {eid}", "ok")
                    else: log(f"WARN {eid}", "warn")
                except Exception as e:
                    log(f"FAIL: {str(e)[:80]}", "fail")
                adaptive_delay.wait()

            # Master shot (uses env ref if available)
            if state["stop"]: break
            done += 1; prog(done, total)
            mp = out / "master_shots" / f"{eid}_master.png"
            if mp.exists():
                log(f"[SKIP] {eid} master")
            else:
                env_ref = out / "environments" / f"{eid}.png"
                refs = [str(env_ref)] if env_ref.exists() else []
                prompt = get_master_shot_prompt(eid)
                if prompt:
                    log(f"[GEN] {eid} MASTER...")
                    try:
                        img = gen_single(client, prompt, refs)
                        if img: mp.write_bytes(img); log(f"OK → {eid}_master", "ok")
                        else: log(f"WARN {eid} master", "warn")
                    except Exception as e:
                        log(f"FAIL: {str(e)[:80]}", "fail")
                    adaptive_delay.wait()

        log("Environments + Masters done!", "ok")
    except Exception as e:
        log(f"PIPELINE ERROR: {str(e)[:120]}", "fail")
    finally:
        state["running"] = False

def run_full_pipeline(key):
    """Auto-chain: Style Anchor → Characters → Envs+Masters → Scenes → Grade → Export.
    Full L1-L12 consistency engine."""
    try:
        if not state["output_dir"]:
            log("ERROR: No storyboard uploaded. Upload a .jsx file first.", "fail"); return
        if not state["panels"]:
            log("ERROR: No panels parsed. Re-upload the storyboard.", "fail"); return
        client = get_client(key)
        out = state["output_dir"]

        # Step 0: Style Anchor (Layer 9)
        style_path = out / "style_anchor" / "style_key.png"
        if not style_path.exists():
            log("STEP 0: STYLE ANCHOR (L9)", "head")
            try:
                img = gen_single(client, get_style_anchor_prompt())
                if img: style_path.write_bytes(img); log("OK → style_key", "ok")
                else: log("WARN: No style anchor generated", "warn")
            except Exception as e:
                log(f"WARN: Style anchor failed: {str(e)[:60]}", "warn")
            adaptive_delay.wait()
        else:
            log("STEP 0: STYLE ANCHOR — done, skipping", "ok")

        # Step 1: Characters (single sheet per character)
        chars = sorted(state["used_chars"])
        chars_total = len(chars)
        chars_remaining = sum(1 for cid in chars if not (out / "characters" / f"@{cid}.png").exists())
        if chars_remaining > 0:
            log(f"STEP 1: CHARACTER SHEETS ({chars_remaining} remaining of {chars_total})", "head")
            done = 0
            for cid in chars:
                if state["stop"]: return
                done += 1; prog(done, chars_total)
                p = out / "characters" / f"@{cid}.png"
                if p.exists(): log(f"[SKIP] @{cid}"); continue
                log(f"[GEN] @{cid} sheet...")
                try:
                    img = gen_single(client, get_char_sheet_prompt(cid))
                    if img: p.write_bytes(img); log(f"OK → @{cid}", "ok")
                    else: log(f"WARN @{cid}", "warn")
                except Exception as e:
                    log(f"FAIL: {str(e)[:80]}", "fail")
                adaptive_delay.wait()
            log("Characters done!", "ok")
        else:
            log("STEP 1: CHARACTERS — all done, skipping", "ok")

        # Step 2: Envs + Masters
        envs = sorted(state["used_envs"])
        envs_remaining = sum(1 for eid in envs if not (out / "environments" / f"{eid}.png").exists() or not (out / "master_shots" / f"{eid}_master.png").exists())
        if envs_remaining > 0:
            log(f"STEP 2: ENVIRONMENTS + MASTERS ({envs_remaining} remaining)", "head")
            done = 0; total = len(envs) * 2
            for eid in envs:
                if state["stop"]: return
                done += 1; prog(done, total)
                p = out / "environments" / f"{eid}.png"
                if p.exists(): log(f"[SKIP] {eid}")
                else:
                    log(f"[GEN] {eid}...")
                    try:
                        img = gen_single(client, get_env_prompt(eid))
                        if img: p.write_bytes(img); log(f"OK → {eid}", "ok")
                    except Exception as e: log(f"FAIL: {str(e)[:80]}", "fail")
                    adaptive_delay.wait()

                if state["stop"]: return
                done += 1; prog(done, total)
                mp = out / "master_shots" / f"{eid}_master.png"
                if mp.exists(): log(f"[SKIP] {eid} master")
                else:
                    env_ref = out / "environments" / f"{eid}.png"
                    refs = [str(env_ref)] if env_ref.exists() else []
                    prompt = get_master_shot_prompt(eid)
                    if prompt:
                        log(f"[GEN] {eid} MASTER...")
                        try:
                            img = gen_single(client, prompt, refs)
                            if img: mp.write_bytes(img); log(f"OK → {eid}_master", "ok")
                        except Exception as e: log(f"FAIL: {str(e)[:80]}", "fail")
                        adaptive_delay.wait()
            log("Environments + Masters done!", "ok")
        else:
            log("STEP 2: ENVS+MASTERS — all done, skipping", "ok")

        # Step 3: Scenes
        log("STEP 3: SCENES", "head")
        state["running"] = True  # keep alive
        mb = state["memory_bank"]
        all_gen = state.get("gen", [])
        remaining = [p for p in all_gen if not any(
            (out / d / f"{p.get('f', p['id'])}.png").exists()
            for d in ["final", "post_processed", "scenes"]
        )]
        if remaining:
            log(f"Generating {len(remaining)} scenes ({len(all_gen) - len(remaining)} already done) — L1-L12", "head")
            # Gather refs
            char_refs = {}
            for cid in get_active_characters():
                sheet = out / "characters" / f"@{cid}.png"
                if sheet.exists():
                    char_refs[cid] = [str(sheet)]
            env_refs = {}
            for eid in get_active_environments():
                master = out / "master_shots" / f"{eid}_master.png"
                basic = out / "environments" / f"{eid}.png"
                if master.exists(): env_refs[eid] = str(master)
                elif basic.exists(): env_refs[eid] = str(basic)

            # Style anchor path (Layer 9)
            style_anchor = out / "style_anchor" / "style_key.png"
            style_ref = str(style_anchor) if style_anchor.exists() else None

            # Section order for cross-section bridge (Layer 10)
            section_order = list(dict.fromkeys(get_section(p) for p in all_gen))

            sections = {}
            for p in all_gen:
                sec = get_section(p)
                if sec not in sections: sections[sec] = []
                pid = p['id']
                all_chars = state["char_map"].get(pid, [])
                env_id = state["env_map"].get(pid); asset = get_asset_type(p)
                fname = f"{p.get('f', pid)}.png"
                primary_char = all_chars[0] if all_chars else None

                # ── Layer 8: ALL character sheet refs ──
                refs = []
                if asset != 'fern':
                    for cid in all_chars:
                        if cid in char_refs:
                            refs.extend(char_refs[cid])
                    if len(refs) > 3: refs = refs[:3]

                # ── Layer 9: Style anchor ──
                if style_ref and len(refs) < 5:
                    refs.append(style_ref)

                # Environment + master refs
                if env_id and env_id in env_refs and asset != 'fern' and len(refs) < 6:
                    refs.extend(mb.get_env_ref(env_id, env_refs.get(env_id)))

                # ── Layer 10: Section bridge ──
                if len(refs) < 6:
                    bridge = mb.get_previous_section_bridge(sec, section_order)
                    if bridge and bridge not in refs:
                        refs.append(bridge)

                # ── Layer 8: Pass all chars to prompt builder ──
                prompt = build_prompt(p, primary_char, env_id, all_chars=all_chars)
                sections[sec].append({
                    "id": pid, "prompt": prompt, "refs": refs,
                    "output": str(out / "scenes" / fname),
                    "info": f"@{','.join(all_chars) if all_chars else '-'} {asset}",
                    "char": primary_char, "all_chars": all_chars, "env": env_id, "stop": False,
                })

            total_scenes = len(all_gen)
            done_n = total_scenes - len(remaining); ok_n = 0; fail_n = 0
            last_output = {}  # track last output per section for L10

            def cb(event, *args):
                nonlocal done_n, ok_n, fail_n
                if event == "generating":
                    done_n += 1; prog(done_n, total_scenes)
                    log(f"[{done_n}/{total_scenes}] {args[0]} {args[1] if len(args)>1 else ''}")
                elif event == "ok":
                    ok_n += 1; pid = args[0]
                    log(f"OK → {pid}", "ok")
                    # Update memory bank for ALL characters in this panel (L8)
                    pd = {pd["id"]: pd for sec in sections.values() for pd in sec}.get(pid)
                    if pd:
                        for cid in pd.get("all_chars", []):
                            mb.update_char(cid, pd["output"])
                        if pd.get("env"):
                            mb.update_env(pd["env"], pd["output"])
                        last_output[get_section_from_pid(pid)] = pd["output"]
                elif event == "skip":
                    done_n += 1; prog(done_n, total_scenes)
                elif event == "fail":
                    fail_n += 1; log(f"FAIL {args[0]}: {args[1] if len(args)>1 else ''}", "fail")

            # Helper to get section from panel ID
            def get_section_from_pid(pid):
                for p in all_gen:
                    if p.get("id") == pid: return get_section(p)
                return ""

            for sec_name, sec_panels in sections.items():
                if state["stop"]: return
                log(f"\n--- {sec_name} ({len(sec_panels)} panels, L1-L12) ---", "head")
                gen_chat_section(client, sec_name, sec_panels, callback=cb)
                # Layer 10: Save last frame as section bridge
                if sec_name in last_output:
                    mb.update_section(sec_name, last_output[sec_name])
            log(f"Scenes done! OK:{ok_n} Fail:{fail_n}", "ok")
        else:
            log("STEP 3: SCENES — all done, skipping", "ok")

        # Step 4: Color Grade
        src = out / "scenes"; dst = out / "post_processed"
        ungraded = [f for f in src.glob("*.png") if not (dst / f.name).exists()]
        if ungraded:
            log(f"STEP 4: COLOR GRADE ({len(ungraded)} new)", "head")
            for i, f in enumerate(ungraded):
                if state["stop"]: return
                prog(i+1, len(ungraded))
                try: post_process(str(f), str(dst / f.name)); log(f"OK → {f.name}", "ok")
                except Exception as e: log(f"FAIL {f.name}: {str(e)[:60]}", "fail")
            final = out / "final"; final.mkdir(exist_ok=True)
            for p in state["panels"]:
                asset = get_asset_type(p)
                if asset in ('media', 'unknown'): continue
                fname = f"{p.get('f', p['id'])}.png"
                s = dst / fname
                if not s.exists(): s = src / fname
                if not s.exists(): continue
                shutil.copy2(str(s), str(final / fname))
            log("Grade + finalize done!", "ok")
        else:
            log("STEP 4: GRADE — all done, skipping", "ok")

        log("FULL PIPELINE COMPLETE ✓", "ok")
    except Exception as e:
        log(f"PIPELINE ERROR: {str(e)[:120]}", "fail")
    finally:
        state["running"] = False

def run_scenes(key, section_filter):
    try:
        if not state["output_dir"] or not state["panels"]:
            log("ERROR: No storyboard uploaded. Upload first.", "fail"); return
        client = get_client(key)
        out = state["output_dir"]
        mb = state["memory_bank"]
        all_gen = state.get("gen", [])

        target = all_gen if section_filter == "__ALL__" else [p for p in all_gen if get_section(p) == section_filter]
        label = "ALL" if section_filter == "__ALL__" else section_filter

        # Gather refs
        char_refs = {}
        for cid in get_active_characters():
            sheet = out / "characters" / f"@{cid}.png"
            if sheet.exists():
                char_refs[cid] = [str(sheet)]

        env_refs = {}
        for eid in get_active_environments():
            master = out / "master_shots" / f"{eid}_master.png"
            basic = out / "environments" / f"{eid}.png"
            if master.exists(): env_refs[eid] = str(master)
            elif basic.exists(): env_refs[eid] = str(basic)

        # Style anchor (Layer 9)
        style_anchor = out / "style_anchor" / "style_key.png"
        style_ref = str(style_anchor) if style_anchor.exists() else None

        # Section order for cross-section bridge (Layer 10)
        section_order = list(dict.fromkeys(get_section(p) for p in all_gen))

        total = len(target)
        log(f"STEP 3: {label} ({total} panels, L1-L13)", "head")

        # Group by section — track index for Layer 13
        sections = {}
        section_panel_idx = {}  # {section: current_index}
        section_panel_totals = {}  # {section: total_count}
        for p in target:
            sec = get_section(p)
            if sec not in sections: sections[sec] = []
            if sec not in section_panel_totals: section_panel_totals[sec] = 0
            section_panel_totals[sec] += 1

        # Initialize section progress in state
        state["section_progress"] = {sec: {"done": 0, "total": section_panel_totals[sec]} for sec in sections}

        panel_sec_index = {}  # {panel_id: index_within_section}
        for p in target:
            sec = get_section(p)
            if sec not in section_panel_idx: section_panel_idx[sec] = 0
            pid = p['id']
            all_chars = state["char_map"].get(pid, [])
            env_id = state["env_map"].get(pid); asset = get_asset_type(p)
            fname = f"{p.get('f', pid)}.png"
            primary_char = all_chars[0] if all_chars else None
            p_idx = section_panel_idx[sec]
            panel_sec_index[pid] = p_idx
            section_panel_idx[sec] += 1

            # Layer 8: ALL character refs
            refs = []
            if asset != 'fern':
                for cid in all_chars:
                    if cid in char_refs:
                        refs.extend(char_refs[cid])
                if len(refs) > 3: refs = refs[:3]

            # Layer 9: Style anchor
            if style_ref and len(refs) < 5:
                refs.append(style_ref)

            # Environment refs
            if env_id and env_id in env_refs and asset != 'fern' and len(refs) < 6:
                refs.extend(mb.get_env_ref(env_id, env_refs.get(env_id)))

            # Layer 10: Section bridge
            if len(refs) < 6:
                bridge = mb.get_previous_section_bridge(sec, section_order)
                if bridge and bridge not in refs:
                    refs.append(bridge)

            # Layer 13: pass section context to build_prompt for cinematography
            prompt = build_prompt(
                p, primary_char, env_id, all_chars=all_chars,
                section_name=sec, panel_index=p_idx,
                section_total=section_panel_totals.get(sec, 20),
                is_first_in_section=(p_idx == 0)
            )
            sections[sec].append({
                "id": pid, "prompt": prompt, "refs": refs,
                "output": str(out / "scenes" / fname),
                "info": f"@{','.join(all_chars) if all_chars else '-'} {asset}",
                "char": primary_char, "all_chars": all_chars, "env": env_id, "stop": False,
            })

        done = 0; ok_n = 0; fail_n = 0
        last_output = {}
        _current_sec = [""]  # mutable for closure

        def cb(event, *args):
            nonlocal done, ok_n, fail_n
            if event == "generating":
                done += 1; prog(done, total)
                pid = args[0]
                state["current_panel"] = pid
                log(f"[{done}/{total}] {pid} {args[1] if len(args)>1 else ''}")
            elif event == "ok":
                ok_n += 1; pid = args[0]
                log(f"OK → {pid}", "ok")
                state["current_panel"] = ""
                # Update section progress
                sec = _current_sec[0]
                if sec and sec in state["section_progress"]:
                    state["section_progress"][sec]["done"] += 1
                pd_map = {pd["id"]: pd for sec in sections.values() for pd in sec}
                if pid in pd_map:
                    pd = pd_map[pid]
                    # L8: Update memory for ALL characters
                    for cid in pd.get("all_chars", []):
                        mb.update_char(cid, pd["output"])
                    if pd.get("env"): mb.update_env(pd["env"], pd["output"])
                    last_output[get_section(next((p for p in target if p["id"]==pid), target[0]))] = pd["output"]
            elif event == "skip":
                done += 1; prog(done, total)
                sec = _current_sec[0]
                if sec and sec in state["section_progress"]:
                    state["section_progress"][sec]["done"] += 1
            elif event == "fail":
                fail_n += 1; log(f"FAIL {args[0]}: {args[1] if len(args)>1 else ''}", "fail")
                state["current_panel"] = ""
            elif event == "warn":
                fail_n += 1; log(f"WARN {args[0]}", "warn")
                state["current_panel"] = ""

        # Stop propagation
        def check_stop():
            while state["running"]:
                time.sleep(1)
                for sp in sections.values():
                    for pd in sp: pd["stop"] = state["stop"]
        threading.Thread(target=check_stop, daemon=True).start()

        for sec_name, sec_panels in sections.items():
            if state["stop"]: break
            _current_sec[0] = sec_name
            state["current_section"] = sec_name
            log(f"\n--- {sec_name} ({len(sec_panels)} panels, L1-L13) ---", "head")
            gen_chat_section(client, sec_name, sec_panels, callback=cb)
            # Layer 10: Save section bridge
            if sec_name in last_output:
                mb.update_section(sec_name, last_output[sec_name])

        state["current_panel"] = ""
        state["current_section"] = ""
        log(f"DONE! OK:{ok_n} Fail:{fail_n}", "ok")
    except Exception as e:
        log(f"SCENES ERROR: {str(e)[:120]}", "fail")
    finally:
        state["running"] = False

def run_color_grade():
    try:
        if not state["output_dir"]:
            log("ERROR: No storyboard uploaded", "fail"); return
        out = state["output_dir"]
        src = out / "scenes"; dst = out / "post_processed"
        files = list(src.glob("*.png"))
        total = len(files)
        log(f"STEP 4: COLOR GRADE ({total})", "head")
        for i, f in enumerate(files):
            if state["stop"]: break
            prog(i+1, total)
            try:
                post_process(str(f), str(dst / f.name))
                log(f"OK → {f.name}", "ok")
            except Exception as e:
                log(f"FAIL {f.name}: {str(e)[:60]}", "fail")

        # Auto-finalize
        log("Finalizing → final/", "head")
        final = out / "final"; final.mkdir(exist_ok=True)
        copied = 0
        for p in state["panels"]:
            asset = get_asset_type(p)
            if asset in ('media', 'unknown'): continue
            fname = f"{p.get('f', p['id'])}.png"
            s = dst / fname
            if not s.exists(): s = src / fname
            if not s.exists(): continue
            shutil.copy2(str(s), str(final / fname)); copied += 1
        log(f"{copied} images → final/", "ok")
    except Exception as e:
        log(f"GRADE ERROR: {str(e)[:120]}", "fail")
    finally:
        state["running"] = False

def run_export():
    try:
        if not state["output_dir"] or not state["panels"]:
            log("ERROR: No storyboard uploaded", "fail"); return
        out = state["output_dir"]
        final_dir = out / "final"; pp_dir = out / "post_processed"; scenes_dir = out / "scenes"

        def find_img(p):
            fname = f"{p.get('f', p['id'])}.png"
            for d in [final_dir, pp_dir, scenes_dir]:
                if (d / fname).exists(): return d / fname
            return None

        log("STEP 5: EXPORTING", "head")
        sections = []; sec_dict = {}
        for p in state["panels"]:
            sec = get_section(p)
            if sec not in sec_dict: sec_dict[sec] = []; sections.append(sec)
            sec_dict[sec].append(p)

        img_count = sum(1 for p in state["panels"] if find_img(p))
        style_name = load_config().get("style", "Unknown")

        html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visual Production Bible</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Sora:wght@600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'DM Sans',sans-serif;background:#07090e;color:#c9d1d9;line-height:1.6}}
.header{{background:#0d1117;padding:24px;border-bottom:1px solid #1c2333;text-align:center}}
.title{{font-family:'Sora',sans-serif;font-size:24px;font-weight:800;background:linear-gradient(135deg,#2dd4bf,#f97316);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:#484f58;font-size:12px;font-family:'JetBrains Mono',monospace;margin-top:4px}}
.section-hdr{{padding:20px;border-bottom:1px solid #1c2333;margin-top:24px;font-family:'Sora',sans-serif;font-size:18px;font-weight:700;color:#f97316}}
.panel{{max-width:900px;margin:16px auto;background:#0d1117;border:1px solid #1c2333;border-radius:12px;overflow:hidden}}
.panel img{{width:100%;display:block;border-bottom:1px solid #1c2333}}
.panel-miss{{width:100%;aspect-ratio:16/9;background:#131820;display:flex;align-items:center;justify-content:center;color:#484f58;border-bottom:1px solid #1c2333}}
.body{{padding:14px 18px}}.badges{{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}}
.b{{padding:2px 8px;border-radius:5px;font-size:10px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.b-id{{background:#1c2333;color:#2dd4bf}}.b-noir{{background:#0f766e33;color:#2dd4bf}}.b-fern{{background:#7c3aed22;color:#a78bfa}}.b-cold{{background:#7f1d1d44;color:#f87171}}
.vo{{background:#131820;border-left:3px solid #2dd4bf;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:13px;color:#e6edf3}}
.meta{{font-size:11px;color:#484f58;margin-top:8px}}.meta span{{color:#8b949e}}
.cam{{background:#0f766e15;border:1px solid #0f766e33;border-radius:6px;padding:8px 12px;margin-top:6px;font-size:11px;color:#2dd4bf}}
</style></head><body>
<div class="header"><div class="title">VISUAL PRODUCTION BIBLE</div>
<div class="sub">v7 · {datetime.now().strftime('%Y-%m-%d %H:%M')} · {style_name} · {len(state["panels"])} panels · {img_count} images</div></div>'''

        for sec in sections:
            html += f'<div class="section-hdr">{sec} ({len(sec_dict[sec])})</div>'
            for p in sec_dict[sec]:
                pid = p.get('id','?'); asset = get_asset_type(p)
                vo = p.get('vo',''); cam = p.get('k','')
                cold = p.get('co', p.get('coldOpen', 0))
                al = {"noir":"Primary","fern":"Secondary"}.get(asset, asset)
                img_path = find_img(p)
                if img_path:
                    b64 = base64.b64encode(img_path.read_bytes()).decode()
                    img_html = f'<img src="data:image/png;base64,{b64}" alt="{pid}">'
                else:
                    img_html = f'<div class="panel-miss">⏳ Not generated</div>'
                html += f'<div class="panel">{img_html}<div class="body"><div class="badges"><span class="b b-id">{pid}</span><span class="b b-{asset}">{al}</span>{"<span class=\'b b-cold\'>COLD OPEN</span>" if cold else ""}</div>'
                if vo: html += f'<div class="vo">🎙 {vo}</div>'
                if cam: html += f'<div class="cam">🎥 {cam}</div>'
                chars = state["char_map"].get(pid, [])
                if chars: html += f'<div class="meta">👤 {", ".join(["@"+c for c in chars])}</div>'
                html += '</div></div>'

        html += '</body></html>'

        path = Path("workspace/storyboard_visual.html")
        path.write_text(html, encoding="utf-8")
        size = path.stat().st_size / 1024 / 1024
        log(f"Exported: {size:.1f} MB", "ok")
    except Exception as e:
        log(f"EXPORT ERROR: {str(e)[:120]}", "fail")
    finally:
        state["running"] = False


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
