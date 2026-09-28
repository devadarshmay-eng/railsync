from functools import lru_cache
from app.adapters.planner.base import BlockPlannerInterface
from app.adapters.planner.deterministic import DeterministicConstraintPlanner
from app.adapters.planner.ortools_planner import OrToolsBlockPlanner
from app.config import settings


@lru_cache(maxsize=1)
def get_block_planner() -> BlockPlannerInterface:
    """Factory returning active block planner interface."""
    solver = settings.PLANNER_DEFAULT_SOLVER.lower()
    if solver == "ortools":
        try:
            return OrToolsBlockPlanner()
        except Exception:
            return DeterministicConstraintPlanner()
    return DeterministicConstraintPlanner()
