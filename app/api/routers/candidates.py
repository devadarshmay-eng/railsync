from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.core.safety import get_safety_headers
from app.db.database import get_db
from app.domain.models import LayaCandidateEvaluation
from app.services.candidate_eval_service import evaluate_candidate_window

router = APIRouter(prefix="/api/candidates", tags=["Candidate Evaluation"])


@router.post("/{candidate_id}/evaluate")
async def evaluate_candidate_endpoint(
    candidate_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """Trigger Second LAYA Decision Point: Assess operational network risk of candidate window."""
    response.headers.update(get_safety_headers())
    try:
        evaluation: LayaCandidateEvaluation = await evaluate_candidate_window(
            db=db,
            candidate_id=candidate_id,
            actor="Section Controller",
        )
        return {"status": "success", "data": evaluation.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
