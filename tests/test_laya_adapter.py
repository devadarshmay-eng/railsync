import pytest
from datetime import datetime, timezone
from app.adapters.laya.mock_adapter import MockLayaAdapter
from app.domain.models import CandidateWindow, IncidentSimulationPayload, NormalizedRequest
from app.domain.constants import IncidentType


def test_laya_triage_decision_structure():
    adapter = MockLayaAdapter()
    req = NormalizedRequest(
        request_id="REQ-TEST-1",
        section_id="TVC-QLN",
        raw_text="Emergency: Rail weld fracture found on mainline km 12/4",
        input_mode="text",
        duration_minutes=120,
        timestamp=datetime.now(timezone.utc)
    )
    decision = adapter.triage_request(req)

    assert decision.department.label == "P-Way"
    assert "P-Way" in decision.department.probabilities
    assert decision.priority.label in ["HIGH", "CRITICAL"]
    assert decision.safety_critical.label is True
    assert decision.safety_critical.probability > 0.5
    assert decision.latency_ms > 0.0
    assert "laya" in decision.model_version


def test_laya_candidate_evaluation_structure():
    adapter = MockLayaAdapter()
    req = NormalizedRequest(
        request_id="REQ-TEST-2",
        section_id="ERS-TCR",
        raw_text="Routine track maintenance",
        input_mode="text",
        duration_minutes=120,
        timestamp=datetime.now(timezone.utc)
    )
    cand = CandidateWindow(
        candidate_id="CW-1",
        request_id="REQ-TEST-2",
        section_id="ERS-TCR",
        start_time_min=120, # 02:00 AM (night off-peak)
        end_time_min=240,
        duration_min=120,
        affected_trains=[],
        conflicts=[],
    )
    eval_res = adapter.evaluate_candidate(req, cand, context={})

    assert eval_res.candidate_id == "CW-1"
    assert eval_res.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert eval_res.confidence >= 0.0
    assert eval_res.latency_ms > 0.0
    assert eval_res.conflicts_high_priority_service is False


def test_laya_incident_evaluation():
    adapter = MockLayaAdapter()
    inc = IncidentSimulationPayload(
        incident_type=IncidentType.TRACK_DEFECT,
        section_id="TVC-QLN",
        description="Track buckle due to high ambient rail temperature",
        expected_delay_min=45
    )
    res = adapter.evaluate_incident(inc, active_blocks=[], context={})

    assert res.incident_type == "TRACK_DEFECT"
    assert res.severity == "HIGH"
    assert res.triggers_reoptimization is True
    assert res.latency_ms > 0.0
