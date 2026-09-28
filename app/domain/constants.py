from enum import Enum


class RequestStatus(str, Enum):
    RECEIVED = "RECEIVED"
    TRIAGED = "TRIAGED"
    PLANNING = "PLANNING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REOPTIMIZATION_REQUIRED = "REOPTIMIZATION_REQUIRED"
    COMPLETED = "COMPLETED"


class Department(str, Enum):
    P_WAY = "P-Way"
    SNT = "S&T"
    TRD_OHE = "TRD/OHE"
    OPERATING = "Operating"
    OTHER = "Other"


class Priority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    CONDITIONAL = "CONDITIONAL"


class ControllerAction(str, Enum):
    APPROVE_REVIEW = "APPROVE_REVIEW"
    SENIOR_REVIEW = "SENIOR_REVIEW"
    REJECT = "REJECT"


class IncidentType(str, Enum):
    TRAIN_DELAY = "TRAIN_DELAY"
    LOCO_FAILURE = "LOCO_FAILURE"
    SIGNAL_MALFUNCTION = "SIGNAL_MALFUNCTION"
    OHE_BREAKDOWN = "OHE_BREAKDOWN"
    TRACK_DEFECT = "TRACK_DEFECT"
    WEATHER = "WEATHER"


class AuditEventType(str, Enum):
    REQUEST_CREATED = "request_created"
    VOICE_INPUT_STARTED = "voice_input_started"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    LAYA_TRIAGE_STARTED = "laya_triage_started"
    LAYA_TRIAGE_COMPLETED = "laya_triage_completed"
    PLANNER_STARTED = "planner_started"
    PLANNER_COMPLETED = "planner_completed"
    LAYA_CANDIDATE_EVALUATED = "laya_candidate_evaluated"
    CONTROLLER_APPROVED = "controller_approved"
    CONTROLLER_REJECTED = "controller_rejected"
    INCIDENT_DETECTED = "incident_detected"
    INCIDENT_CREATED = "incident_created"
    INCIDENT_EVALUATED = "incident_evaluated"
    ACTIVE_BLOCK_AFFECTED = "active_block_affected"
    REOPTIMIZATION_TRIGGERED = "reoptimization_triggered"
    REOPTIMIZATION_COMPLETED = "reoptimization_completed"
    REOPTIMIZATION_NOT_REQUIRED = "reoptimization_not_required"


# Safety Disclaimer constant for headers & responses
SAFETY_DISCLAIMER = (
    "ADVISORY ONLY. HUMAN CONTROLLER APPROVAL REQUIRED. "
    "RAILSYNC AI DOES NOT CONTROL SIGNALING, INTERLOCKING OR KAVACH."
)
