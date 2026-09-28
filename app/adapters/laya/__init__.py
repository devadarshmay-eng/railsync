from functools import lru_cache
from app.adapters.laya.base import LayaAdapterInterface
from app.adapters.laya.current_adapter import CurrentLayaAdapter
from app.adapters.laya.finetuned_adapter import FineTunedLayaAdapter
from app.adapters.laya.mock_adapter import MockLayaAdapter
from app.config import settings


@lru_cache(maxsize=1)
def get_laya_adapter() -> LayaAdapterInterface:
    """Factory returning the active LAYA adapter based on environment configuration."""
    mode = settings.LAYA_MODE.lower()
    
    if mode == "live":
        try:
            return CurrentLayaAdapter(
                model_id_or_path=settings.LAYA_MODEL_PATH,
                device=settings.LAYA_DEVICE
            )
        except Exception:
            # Fallback to calibrated mock if weights cannot be reached
            return MockLayaAdapter(model_version=f"{settings.LAYA_MODEL_PATH}@fallback")
            
    elif mode == "finetuned":
        return FineTunedLayaAdapter(
            model_id_or_path=settings.LAYA_FINETUNED_PATH,
            device=settings.LAYA_DEVICE
        )
    else:
        return MockLayaAdapter()
