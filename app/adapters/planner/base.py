from abc import ABC, abstractmethod
from typing import Any, Dict, List
from app.domain.models import CandidateWindow, NormalizedRequest, TrainModel


class BlockPlannerInterface(ABC):
    """Interface for deterministic and constraint-based railway maintenance block planners."""

    @abstractmethod
    def plan_candidate_windows(
        self,
        request: NormalizedRequest,
        timetable: List[TrainModel],
        existing_blocks: List[Dict[str, Any]],
        horizon_minutes: int = 2880, # 48 hours
        max_candidates: int = 5,
    ) -> List[CandidateWindow]:
        """Generate feasible candidate maintenance windows ranked by optimality score."""
        pass

    @abstractmethod
    def get_solver_name(self) -> str:
        """Returns the solver name and version."""
        pass
