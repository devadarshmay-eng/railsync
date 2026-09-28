from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from app.db.seed import MAINTENANCE_PRESETS, SECTIONS
from app.domain.models import NormalizedRequest, RequestCreatePayload

# Map frontend prototype maintenance type IDs to backend preset keys
UI_TYPE_ALIASES = {
    "track_repair": "track_defect_weld",
    "bridge_work": "bridge_bearing_greasing",
    "ohe_maint": "ohe_catenary_replacement",
    "power_sub": "substation_transformer_oil",
    "point_machine": "signal_point_machine",
    "signal_maint": "track_circuit_failure",
    "building_work": "deep_screening_ballast",
}


def normalize_request_input(payload: RequestCreatePayload) -> NormalizedRequest:
    """
    Normalizes preset, free-text, and voice maintenance submissions into a single
    canonical NormalizedRequest schema. Validates input bounds defensively.
    """
    now = datetime.now(timezone.utc)
    req_id = f"MR-{now.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"

    # 1. Section extraction and validation
    raw_sec = payload.section or payload.section_id
    if not raw_sec or not raw_sec.strip():
        # Attempt to infer section from spoken transcript or text (e.g., 'TVC' and 'QLN')
        candidate_text = (payload.free_text or payload.raw_text or "").upper()
        for sec_key in SECTIONS.keys():
            parts = sec_key.split("-")
            if (parts[0] in candidate_text and parts[1] in candidate_text) or sec_key in candidate_text:
                raw_sec = sec_key
                break
        if not raw_sec:
            raise ValueError("Section is required for maintenance requests.")

    sec_id = raw_sec.strip().upper()
    if sec_id not in SECTIONS:
        # Check bidirectional / reverse direction (e.g., QLN-TVC -> TVC-QLN)
        parts = sec_id.split("-")
        if len(parts) == 2 and f"{parts[1]}-{parts[0]}" in SECTIONS:
            sec_id = f"{parts[1]}-{parts[0]}"
        else:
            valid_secs = ", ".join(list(SECTIONS.keys())[:6]) + "..."
            raise ValueError(f"Unknown railway section: '{raw_sec}'. Expected one of: {valid_secs}")

    # 2. Preset / Maintenance Type resolution
    raw_type = (
        payload.preset_type
        or payload.maintenance_type
        or payload.work_type
    )
    resolved_type: Optional[str] = None
    preset_data = None

    if raw_type:
        clean_type = raw_type.strip().lower()
        if clean_type in MAINTENANCE_PRESETS:
            resolved_type = clean_type
            preset_data = MAINTENANCE_PRESETS[clean_type]
        elif clean_type in UI_TYPE_ALIASES:
            mapped_key = UI_TYPE_ALIASES[clean_type]
            resolved_type = mapped_key
            preset_data = MAINTENANCE_PRESETS.get(mapped_key)
        else:
            resolved_type = clean_type

    # 3. Duration validation
    dur_input = payload.duration if payload.duration is not None else payload.duration_minutes
    if dur_input is not None:
        if dur_input <= 0:
            raise ValueError("Duration must be a positive number of minutes (greater than 0).")
        duration = int(dur_input)
    elif preset_data and "default_duration_min" in preset_data:
        duration = int(preset_data["default_duration_min"])
    else:
        duration = 120

    # 4. Text synthesis (Preset description + optional free-text notes)
    free_text = (payload.free_text or payload.raw_text or "").strip()
    if preset_data:
        preset_desc = f"Preset: {preset_data['name']} - {preset_data['description']}"
        if free_text and free_text != preset_desc:
            raw_text = f"{preset_desc} | Operator Notes: {free_text}"
        else:
            raw_text = preset_desc
    else:
        if not free_text:
            raise ValueError("Either a valid maintenance work type or a descriptive text must be provided.")
        raw_text = free_text

    # 5. Department resolution (payload takes priority, preset fallback)
    department = payload.department
    if not department and preset_data:
        department = preset_data.get("department")

    # 6. Priority resolution
    priority = (payload.priority or "").upper() if payload.priority else None
    if priority and priority not in ["LOW", "NORMAL", "MED", "HIGH", "CRITICAL"]:
        priority = "NORMAL"
    elif priority == "MED":
        priority = "NORMAL"

    # 7. Input mode determination
    if payload.input_mode:
        input_mode = payload.input_mode
    elif resolved_type:
        input_mode = "preset"
    else:
        input_mode = "text"

    return NormalizedRequest(
        request_id=req_id,
        section=sec_id,
        section_id=sec_id,
        asset_id=payload.asset_id,
        maintenance_type=resolved_type,
        preset_type=resolved_type,
        department=department,
        priority=priority,
        duration=duration,
        duration_minutes=duration,
        raw_text=raw_text,
        input_mode=input_mode,
        language=payload.language or "en",
        timestamp=now,
        metadata=payload.metadata or {},
    )
