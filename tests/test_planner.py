import pytest
from datetime import datetime, timezone
from app.adapters.planner.deterministic import DeterministicConstraintPlanner
from app.adapters.planner.ortools_planner import OrToolsBlockPlanner
from app.db.seed import TRAIN_TIMETABLE
from app.domain.models import NormalizedRequest


@pytest.fixture
def sample_request():
    return NormalizedRequest(
        request_id="REQ-PLAN-001",
        section_id="TVC-QLN",
        raw_text="Track rail renewal",
        input_mode="text",
        duration_minutes=120,
        preset_type="track_defect_weld",
        timestamp=datetime.now(timezone.utc)
    )


def test_deterministic_planner(sample_request):
    planner = DeterministicConstraintPlanner(slot_step_min=30)
    candidates = planner.plan_candidate_windows(
        request=sample_request,
        timetable=TRAIN_TIMETABLE,
        existing_blocks=[],
        horizon_minutes=1440, # 24 hours
        max_candidates=3
    )

    assert len(candidates) > 0
    assert len(candidates) <= 3
    for c in candidates:
        assert c.section_id == "TVC-QLN"
        assert c.duration_min == 120
        assert c.end_time_min == c.start_time_min + 120
        assert c.planner_latency_ms > 0.0
        assert c.optimality_score >= 0.0


def test_ortools_cp_sat_planner(sample_request):
    planner = OrToolsBlockPlanner(time_limit_seconds=2.0)
    candidates = planner.plan_candidate_windows(
        request=sample_request,
        timetable=TRAIN_TIMETABLE,
        existing_blocks=[],
        horizon_minutes=1440,
        max_candidates=3
    )

    assert len(candidates) > 0
    assert len(candidates) <= 3
    for c in candidates:
        assert c.section_id == "TVC-QLN"
        assert c.duration_min == 120
        assert c.end_time_min == c.start_time_min + 120
        assert c.planner_latency_ms > 0.0
