import time
from typing import Any, Dict
import laya
from app.adapters.laya.base import LayaAdapterInterface
from app.adapters.laya.prompts import (
    get_candidate_evaluation_questions,
    get_incident_evaluation_questions,
    get_triage_questions,
)
from app.domain.constants import ControllerAction
from app.domain.models import (
    CandidateWindow,
    DepartmentDistribution,
    IncidentEvaluationDecision,
    IncidentSimulationPayload,
    LayaCandidateEvaluation,
    LayaTriageDecision,
    NormalizedRequest,
    PriorityDistribution,
    SafetyCriticalDecision,
)


class CurrentLayaAdapter(LayaAdapterInterface):
    """Adapter for the open LAYA model checkpoint (convaiinnovations/laya)."""

    def __init__(self, model_id_or_path: str = "convaiinnovations/laya", device: str = "cpu"):
        self.model_id = model_id_or_path
        self.device = device
        self._load_agent()

    def _load_agent(self) -> None:
        try:
            self.agent = laya.load(self.model_id, device=self.device)
            self.is_loaded = True
            self.load_error = None
        except Exception as e:
            self.is_loaded = False
            self.load_error = str(e)

    def triage_request(self, request: NormalizedRequest) -> LayaTriageDecision:
        if not getattr(self, "is_loaded", False):
            raise RuntimeError(
                f"LAYA agent is not loaded or unavailable: {getattr(self, 'load_error', 'unknown initialization failure')}"
            )

        t0 = time.perf_counter()
        state = {
            "request_id": request.request_id,
            "section": request.section,
            "text": request.raw_text,
            "preset_type": request.preset_type or request.maintenance_type or "none",
            "duration_minutes": request.duration,
            "department_hint": request.department or "none",
            "priority_hint": request.priority or "none",
        }
        questions = get_triage_questions()
        
        try:
            result = self.agent.predict(state, questions)
        except Exception as exc:
            raise RuntimeError(f"LAYA inference error during triage: {exc}") from exc

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        answers = result.get("answers", {})

        # Department classification
        dept_ans = answers.get("department", {})
        dept_choice = dept_ans.get("choice") or request.department or "P-Way"
        dept_probs = dept_ans.get("probabilities") # dict of float or None

        # Priority classification
        prio_ans = answers.get("priority", {})
        prio_choice = prio_ans.get("choice") or request.priority or "NORMAL"
        prio_probs = prio_ans.get("probabilities") # dict of float or None

        # Safety criticality prediction
        safety_ans = answers.get("safety_critical", {})
        safety_val = safety_ans.get("noul")
        if safety_val is not None:
            safety_prob = round(float(safety_val), 4)
            safety_label = safety_prob >= 0.5
        else:
            safety_prob = None
            safety_label = prio_choice in ["HIGH", "CRITICAL"]

        probs_avail = bool(dept_probs is not None and prio_probs is not None and safety_prob is not None)

        return LayaTriageDecision(
            department=DepartmentDistribution(label=dept_choice, probabilities=dept_probs),
            priority=PriorityDistribution(label=prio_choice, probabilities=prio_probs),
            safety_critical=SafetyCriticalDecision(label=safety_label, probability=safety_prob),
            latency_ms=elapsed_ms,
            model_version=f"{self.model_id}@0.3.20",
            probabilities_available=probs_avail,
        )

    def evaluate_candidate(
        self,
        request: NormalizedRequest,
        candidate: CandidateWindow,
        context: Dict[str, Any]
    ) -> LayaCandidateEvaluation:
        t0 = time.perf_counter()
        state = {
            "section": request.section_id,
            "duration": request.duration_minutes,
            "start_time_min": candidate.start_time_min,
            "end_time_min": candidate.end_time_min,
            "affected_trains": candidate.affected_trains,
            "conflicts": candidate.conflicts,
            "context": context,
        }
        questions = get_candidate_evaluation_questions()
        
        result = self.agent.predict(state, questions)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        answers = result.get("answers", {})

        risk_ans = answers.get("risk_level", {})
        risk_choice = risk_ans.get("choice", "MEDIUM")
        risk_probs = risk_ans.get("probabilities") # True probabilities or None (NO fabrication)

        high_prio_ans = answers.get("conflicts_high_priority_service", {})
        high_prio_prob = high_prio_ans.get("noul")
        if high_prio_prob is not None:
            high_prio_flag = float(high_prio_prob) >= 0.5
        else:
            high_prio_flag = any(any(k in t.upper() for k in ["VB", "JSH", "EXP", "SF", "SUPERFAST", "VANDE"]) for t in candidate.affected_trains)

        action_ans = answers.get("recommended_action", {})
        action_choice = action_ans.get("choice", "APPROVE_REVIEW")
        confidence = action_ans.get("confidence")

        sh = (candidate.start_time_min // 60) % 24
        sm = candidate.start_time_min % 60
        eh = (candidate.end_time_min // 60) % 24
        em = candidate.end_time_min % 60
        conflict_interp = (
            f"Evaluated window [{sh:02d}:{sm:02d} - {eh:02d}:{em:02d}] on {request.section_id}: "
            f"{len(candidate.affected_trains)} service(s) regulated."
        )

        return LayaCandidateEvaluation(
            candidate_id=candidate.candidate_id,
            risk_level=risk_choice,
            risk_probabilities=risk_probs,
            conflicts_high_priority_service=high_prio_flag,
            recommended_action=ControllerAction(action_choice),
            confidence=confidence,
            latency_ms=elapsed_ms,
            model_version=f"{self.model_id}@0.3.20",
            conflict_interpretation=conflict_interp,
            review_recommendation=action_choice,
        )

    def evaluate_incident(
        self,
        incident: IncidentSimulationPayload,
        active_blocks: list,
        context: Dict[str, Any]
    ) -> IncidentEvaluationDecision:
        t0 = time.perf_counter()
        state = {
            "incident_type": incident.incident_type.value,
            "section": incident.section_id,
            "description": incident.description,
            "train_no": incident.train_no,
            "expected_delay_min": incident.expected_delay_min,
            "active_blocks_count": len(active_blocks),
            "context": context,
        }
        questions = get_incident_evaluation_questions()
        
        result = self.agent.predict(state, questions)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        answers = result.get("answers", {})

        sev_ans = answers.get("severity", {})
        sev_choice = sev_ans.get("choice", "MEDIUM")
        
        affects_ans = answers.get("affects_active_block", {})
        affects_flag = affects_ans.get("noul", 0.0) >= 0.5

        reopt_ans = answers.get("triggers_reoptimization", {})
        reopt_flag = reopt_ans.get("noul", 0.0) >= 0.5
        confidence = reopt_ans.get("confidence", 0.8)

        return IncidentEvaluationDecision(
            incident_type=incident.incident_type.value,
            severity=sev_choice,
            affects_active_block=affects_flag,
            triggers_reoptimization=reopt_flag,
            affected_sections=[s for s in [incident.section_id] if s] or ["ERS-TCR"],
            confidence=confidence,
            latency_ms=elapsed_ms,
            model_version=f"{self.model_id}@laya-0.3.20",
        )

    def get_model_metadata(self) -> Dict[str, Any]:
        return {
            "adapter": "CurrentLayaAdapter",
            "model_id": self.model_id,
            "device": self.device,
            "is_loaded": getattr(self, "is_loaded", False),
        }
