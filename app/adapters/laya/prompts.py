"""LAYA Question Definitions for Structured Decision Making.

Follows the non-autoregressive typed question schema of Laya:
- choice: categorical classification with calibrated softmax probabilities
- noul: calibrated binary decision returning P(true)
"""

from typing import Any, Dict


def get_triage_questions() -> Dict[str, Dict[str, Any]]:
    return {
        "department": {
            "type": "choice",
            "instructions": "Which Indian Railways department is responsible for executing this maintenance work?",
            "criteria": {
                "P-Way": "Permanent Way, Civil engineering, rails, sleepers, ballast packing, turnout track welds, formations, bridges.",
                "S&T": "Signal and Telecommunication, track circuits, point machines, signal aspects, relays, axle counters, electronic interlocking.",
                "TRD/OHE": "Traction Distribution, overhead catenary, contact wire, pantograph interface, electrical substations, isolators.",
                "Operating": "Traffic department, yard movements, shunting operations, platform regulation, station master operations.",
                "Other": "Station general facilities, sanitation, non-operational civil structures, lighting.",
            },
        },
        "priority": {
            "type": "choice",
            "instructions": "What is the operational priority level for this maintenance work?",
            "criteria": {
                "LOW": "Routine inspection, cosmetic upkeep, non-traffic-disrupting maintenance that can wait several days.",
                "NORMAL": "Standard scheduled periodic maintenance to be planned within 24 to 48 hours.",
                "HIGH": "Significant track or asset degradation threatening speed restrictions or secondary delay.",
                "CRITICAL": "Imminent rail fracture, weld failure, signal blanking, or catenary snap posing urgent safety hazard.",
            },
        },
        "safety_critical": {
            "type": "noul",
            "instructions": "Is this issue safety-critical that could cause a derailment, collision, or immediate hazard to train operations if not addressed?",
            "criteria": {
                "true": "Direct threat to track integrity, train stability, or signal fail-safety.",
                "false": "Standard preventative upkeep or minor operational defect with no imminent derailment risk.",
            },
        },
    }


def get_candidate_evaluation_questions() -> Dict[str, Dict[str, Any]]:
    return {
        "risk_level": {
            "type": "choice",
            "instructions": "What is the operational network disruption risk of granting this candidate maintenance block window?",
            "criteria": {
                "LOW": "Off-peak or deep-night window (01:00-05:00) with zero or minimal passenger train regulation.",
                "MEDIUM": "Moderate delay to freight traffic or single non-peak passenger express regulated with minor delay.",
                "HIGH": "Multiple passenger trains regulated or conflicts with busy morning/evening commuter peak.",
                "CRITICAL": "Severe bottleneck disruption affecting high-speed corridors or multiple premium express services.",
            },
        },
        "conflicts_high_priority_service": {
            "type": "noul",
            "instructions": "Does this maintenance window conflict with or cause regulation to high-priority premium passenger services (e.g. Vande Bharat, Jan Shatabdi, Rajdhani, Superfast Express)?",
            "criteria": {
                "true": "At least one premium or superfast passenger train is delayed or halted by the proposed block.",
                "false": "Only freight trains or no trains are present in the section during the block.",
            },
        },
        "recommended_action": {
            "type": "choice",
            "instructions": "What recommendation should be presented to the Section Controller regarding this candidate maintenance block?",
            "criteria": {
                "APPROVE_REVIEW": "Feasible window with minimal network delay; recommend controller approval.",
                "SENIOR_REVIEW": "Elevated conflict or tight margin requiring senior divisional controller concurrence.",
                "REJECT": "Unacceptable passenger disruption, heavy delay cascade, or infeasible operational timing; reject or re-optimize.",
            },
        },
    }


def get_incident_evaluation_questions() -> Dict[str, Dict[str, Any]]:
    return {
        "severity": {
            "type": "choice",
            "instructions": "What is the operational severity of this reported railway incident?",
            "criteria": {
                "LOW": "Minor delay under 15 minutes, non-critical sensor alarm, or auxiliary system warning.",
                "MEDIUM": "Significant delay (15-45 minutes) on a double-line section with single-line working feasible.",
                "HIGH": "Total section blockage exceeding 45 minutes, locomotive stalling, or power trip on trunk route.",
                "CRITICAL": "Track fracture, collision hazard, OHE line collapse, or derailment requiring emergency cordon.",
            },
        },
        "affects_active_block": {
            "type": "noul",
            "instructions": "Does this incident directly disrupt, intersect, or invalidate any currently approved or active maintenance block?",
            "criteria": {
                "true": "The incident occurs in or immediately adjacent to an active maintenance block section.",
                "false": "The incident is isolated from active maintenance blocks.",
            },
        },
        "triggers_reoptimization": {
            "type": "noul",
            "instructions": "Does this incident necessitate an immediate re-optimization and recalculation of downstream maintenance block windows?",
            "criteria": {
                "true": "Timetable regulation and delayed rakes will collide with scheduled maintenance windows downstream.",
                "false": "Normal train running can recover via regulation without perturbing the maintenance plan.",
            },
        },
    }
