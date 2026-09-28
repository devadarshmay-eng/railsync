from abc import ABC, abstractmethod
from typing import Any, Dict
from app.domain.models import (
    CandidateWindow,
    IncidentEvaluationDecision,
    IncidentSimulationPayload,
    LayaCandidateEvaluation,
    LayaTriageDecision,
    NormalizedRequest,
)


class LayaAdapterInterface(ABC):
    """Abstract adapter contract for LAYA structured decision-making engine."""

    @abstractmethod
    def triage_request(self, request: NormalizedRequest) -> LayaTriageDecision:
        """First decision point: Request triage (department, priority, safety_critical)."""
        pass

    @abstractmethod
    def evaluate_candidate(
        self,
        request: NormalizedRequest,
        candidate: CandidateWindow,
        context: Dict[str, Any]
    ) -> LayaCandidateEvaluation:
        """Second decision point: Operational risk assessment of a candidate block window."""
        pass

    @abstractmethod
    def evaluate_incident(
        self,
        incident: IncidentSimulationPayload,
        active_blocks: list,
        context: Dict[str, Any]
    ) -> IncidentEvaluationDecision:
        """What-if decision point: Assess disruption severity and reoptimization need."""
        pass

    @abstractmethod
    def get_model_metadata(self) -> Dict[str, Any]:
        """Return model metadata, version, and execution device."""
        pass
