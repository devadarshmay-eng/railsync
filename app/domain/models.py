from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from app.domain.constants import (
    ControllerAction,
    Department,
    FeasibilityStatus,
    IncidentType,
    Priority,
    RequestStatus,
)


class NormalizedRequest(BaseModel):
    """Normalized schema converging preset, free-text, and voice maintenance inputs."""
    request_id: str
    section: str = ""
    section_id: str = ""
    asset_id: Optional[str] = None
    maintenance_type: Optional[str] = None
    preset_type: Optional[str] = None
    department: Optional[str] = None
    priority: Optional[str] = None
    duration: int = 120
    duration_minutes: int = 120
    raw_text: str
    input_mode: Literal["preset", "text", "voice"]
    language: str = "en"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_aliases(self) -> "NormalizedRequest":
        if not self.section and self.section_id:
            self.section = self.section_id
        elif not self.section_id and self.section:
            self.section_id = self.section
        
        if not self.maintenance_type and self.preset_type:
            self.maintenance_type = self.preset_type
        elif not self.preset_type and self.maintenance_type:
            self.preset_type = self.maintenance_type

        if self.duration and not self.duration_minutes:
            self.duration_minutes = self.duration
        elif self.duration_minutes and not self.duration:
            self.duration = self.duration_minutes
        return self


class RequestCreatePayload(BaseModel):
    section: Optional[str] = None
    section_id: Optional[str] = None
    raw_text: Optional[str] = None
    free_text: Optional[str] = None
    department: Optional[str] = None
    work_type: Optional[str] = None
    maintenance_type: Optional[str] = None
    preset_type: Optional[str] = None
    priority: Optional[str] = None
    duration: Optional[int] = None
    duration_minutes: Optional[int] = None
    asset_id: Optional[str] = None
    language: Optional[str] = "en"
    input_mode: Optional[Literal["preset", "text", "voice"]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    auto_triage: bool = False


class DepartmentDistribution(BaseModel):
    label: str
    probabilities: Optional[Dict[str, float]] = None


class PriorityDistribution(BaseModel):
    label: str
    probabilities: Optional[Dict[str, float]] = None


class SafetyCriticalDecision(BaseModel):
    label: bool
    probability: Optional[float] = None


class LayaTriageDecision(BaseModel):
    department: DepartmentDistribution
    priority: PriorityDistribution
    safety_critical: SafetyCriticalDecision
    latency_ms: float
    model_version: str
    probabilities_available: bool = True


class CandidateWindow(BaseModel):
    candidate_id: str
    request_id: str
    section: str = ""
    section_id: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    start_time_min: int = 0
    end_time_min: int = 0
    duration: int = 120
    duration_min: int = 120
    feasible: bool = True
    affected_services: List[str] = Field(default_factory=list)
    affected_trains: List[str] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    feasibility_status: FeasibilityStatus = FeasibilityStatus.FEASIBLE
    optimality_score: float = 0.0
    violated_constraints: List[str] = Field(default_factory=list)
    constraint_violations: List[str] = Field(default_factory=list)
    planner_version: str = "DeterministicConstraintPlanner@1.0"
    planner_latency_ms: float = 0.0
    laya_evaluation: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def sync_candidate_fields(self) -> "CandidateWindow":
        if not self.section and self.section_id:
            self.section = self.section_id
        elif not self.section_id and self.section:
            self.section_id = self.section

        if not self.duration and self.duration_min:
            self.duration = self.duration_min
        elif not self.duration_min and self.duration:
            self.duration_min = self.duration

        if not self.affected_services and self.affected_trains:
            self.affected_services = self.affected_trains
        elif not self.affected_trains and self.affected_services:
            self.affected_trains = self.affected_services

        if not self.violated_constraints and self.constraint_violations:
            self.violated_constraints = self.constraint_violations
        elif not self.constraint_violations and self.violated_constraints:
            self.constraint_violations = self.violated_constraints

        if not self.start_time:
            sh = (self.start_time_min // 60) % 24
            sm = self.start_time_min % 60
            day_str = f"Day {(self.start_time_min // 1440) + 1} " if self.start_time_min >= 1440 else ""
            self.start_time = f"{day_str}{sh:02d}:{sm:02d}"

        if not self.end_time:
            eh = (self.end_time_min // 60) % 24
            em = self.end_time_min % 60
            day_str = f"Day {(self.end_time_min // 1440) + 1} " if self.end_time_min >= 1440 else ""
            self.end_time = f"{day_str}{eh:02d}:{em:02d}"

        self.feasible = self.feasibility_status != FeasibilityStatus.INFEASIBLE
        return self


class LayaCandidateEvaluation(BaseModel):
    candidate_id: str
    risk_level: str
    risk_probabilities: Optional[Dict[str, float]] = None
    conflicts_high_priority_service: bool = False
    recommended_action: ControllerAction = ControllerAction.APPROVE_REVIEW
    confidence: Optional[float] = None
    latency_ms: float = 0.0
    model_version: str = "convaiinnovations/laya@0.3.20"
    conflict_interpretation: Optional[str] = None
    review_recommendation: Optional[str] = None


class ControllerDecisionPayload(BaseModel):
    candidate_id: Optional[str] = None
    actor_name: str = "Chief Controller"
    actor_role: str = "Section Controller"
    reason: Optional[str] = None
    checklist: Optional[Dict[str, bool]] = None


class IncidentSimulationPayload(BaseModel):
    incident_type: IncidentType = IncidentType.TRAIN_DELAY
    section_id: Optional[str] = None
    description: Optional[str] = None
    train_no: Optional[str] = None
    expected_delay_min: Optional[int] = 30
    delay_min: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize delay
            if "delay_min" in data and ("expected_delay_min" not in data or data["expected_delay_min"] is None):
                data["expected_delay_min"] = data["delay_min"]
            elif "expected_delay_min" in data and ("delay_min" not in data or data["delay_min"] is None):
                data["delay_min"] = data["expected_delay_min"]

            # Map user/frontend incident string labels to IncidentType enum
            inc_type = data.get("incident_type")
            if isinstance(inc_type, str):
                type_map = {
                    "Loco Failure": "LOCO_FAILURE",
                    "LOCO": "LOCO_FAILURE",
                    "Signal Malfunction": "SIGNAL_MALFUNCTION",
                    "SIGNAL": "SIGNAL_MALFUNCTION",
                    "OHE Issue": "OHE_BREAKDOWN",
                    "OHE Breakdown": "OHE_BREAKDOWN",
                    "OHE": "OHE_BREAKDOWN",
                    "Track Defect": "TRACK_DEFECT",
                    "TRACK": "TRACK_DEFECT",
                    "Train Delay": "TRAIN_DELAY",
                    "DELAY": "TRAIN_DELAY",
                    "Weather": "WEATHER",
                }
                if inc_type in type_map:
                    data["incident_type"] = type_map[inc_type]

            if not data.get("description"):
                t_no = data.get("train_no", "Corridor Service")
                d_min = data.get("expected_delay_min", 30)
                data["description"] = f"{data.get('incident_type', 'TRAIN_DELAY')} incident on {t_no} (+{d_min}m)"
        return data


class IncidentEvaluationDecision(BaseModel):
    incident_type: str
    severity: str
    affects_active_block: bool
    triggers_reoptimization: bool
    affected_sections: List[str]
    confidence: float
    latency_ms: float
    model_version: str


class DisruptionSimulationResult(BaseModel):
    incident_id: str
    incident_type: str
    train_no: Optional[str] = None
    delay_min: int = 0
    section_id: str
    physical_collision_detected: bool
    collision_details: List[Dict[str, Any]] = Field(default_factory=list)
    affects_active_block: bool
    triggers_reoptimization: bool
    affected_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    reoptimization_status: str # "COMPLETED" or "NOT_REQUIRED"
    new_candidates: List[CandidateWindow] = Field(default_factory=list)
    laya_incident_decision: IncidentEvaluationDecision
    mitigation_strategies: List[Dict[str, str]] = Field(default_factory=list)
    latency_ms: float = 0.0


class ASRResult(BaseModel):
    transcript: str
    detected_language: str
    confidence: float
    latency_ms: float
    audio_duration_ms: float


class AuditEventRecord(BaseModel):
    event_id: str
    event_type: str
    timestamp: datetime
    request_id: Optional[str] = None
    actor: str = "system"
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    model_version: Optional[str] = None
    latency_ms: Optional[float] = None
    decision: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Demo Domain Schemas
class StationModel(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    master: str


class SectionModel(BaseModel):
    id: str
    from_station: str
    to_station: str
    km: int
    lines: int
    zone: str = "SR"


class TrainScheduleEntry(BaseModel):
    station: str
    time_min: int


class SectionOccupancy(BaseModel):
    section_id: str
    t0_min: int
    t1_min: int


class TrainModel(BaseModel):
    no: str
    name: str
    type: str # JSH, SUP, EXP, MEM, FRT
    route: List[str] = Field(default_factory=list)
    dep_min: int = 0
    speed_kmh: int = 80
    schedule: List[TrainScheduleEntry] = Field(default_factory=list)
    occupancies: List[SectionOccupancy] = Field(default_factory=list)
    delay_min: int = 0
