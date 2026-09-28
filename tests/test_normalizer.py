import pytest
from app.domain.models import RequestCreatePayload
from app.services.input_normalizer import normalize_request_input


def test_preset_input_normalization():
    payload = RequestCreatePayload(
        section_id="TVC-QLN",
        preset_type="track_defect_weld",
        input_mode="preset"
    )
    req = normalize_request_input(payload)
    assert req.section == "TVC-QLN"
    assert req.section_id == "TVC-QLN"
    assert req.preset_type == "track_defect_weld"
    assert req.maintenance_type == "track_defect_weld"
    assert "Track Rail Weld Defect" in req.raw_text
    assert req.duration == 120
    assert req.duration_minutes == 120
    assert req.department == "P-Way"
    assert req.request_id.startswith("MR-")


def test_free_text_normalization():
    payload = RequestCreatePayload(
        section_id="ERS-TCR",
        free_text="Broken insulator observed on down line mast 45/12 near Aluva",
        input_mode="text",
        duration=90,
        department="TRD/OHE",
        priority="HIGH",
    )
    req = normalize_request_input(payload)
    assert req.section == "ERS-TCR"
    assert req.duration == 90
    assert "Broken insulator" in req.raw_text
    assert req.department == "TRD/OHE"
    assert req.priority == "HIGH"
    assert req.language == "en"
    assert req.input_mode == "text"


def test_bidirectional_section_normalization():
    # Reverse section QLN-TVC should normalize to TVC-QLN
    payload = RequestCreatePayload(
        section="QLN-TVC",
        free_text="Track inspection required",
    )
    req = normalize_request_input(payload)
    assert req.section == "TVC-QLN"
    assert req.section_id == "TVC-QLN"


def test_invalid_request_handling_missing_section():
    payload = RequestCreatePayload(
        free_text="Rail crack identified",
        duration=60,
    )
    with pytest.raises(ValueError, match="Section is required"):
        normalize_request_input(payload)


def test_invalid_request_handling_unknown_section():
    payload = RequestCreatePayload(
        section="UNKNOWN-STATION",
        free_text="Rail crack identified",
    )
    with pytest.raises(ValueError, match="Unknown railway section"):
        normalize_request_input(payload)


def test_invalid_request_handling_negative_duration():
    payload = RequestCreatePayload(
        section="TVC-QLN",
        free_text="Maintenance work",
        duration=-30,
    )
    with pytest.raises(ValueError, match="Duration must be a positive number"):
        normalize_request_input(payload)


def test_invalid_request_handling_empty_content():
    payload = RequestCreatePayload(
        section="TVC-QLN",
        duration=60,
    )
    with pytest.raises(ValueError, match="Either a valid maintenance work type or a descriptive text must be provided"):
        normalize_request_input(payload)
