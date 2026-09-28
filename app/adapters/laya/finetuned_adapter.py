from typing import Any, Dict
from app.adapters.laya.current_adapter import CurrentLayaAdapter


class FineTunedLayaAdapter(CurrentLayaAdapter):
    """Adapter for the future Indian Railways domain-fine-tuned LAYA checkpoint.

    Inherits the exact contract from CurrentLayaAdapter. When domain checkpoint weights
    are placed in the specified directory, this adapter loads them without changing
    any services, routes, or domain models.
    """

    def __init__(self, model_id_or_path: str = "./models/laya-ir-checkpoint", device: str = "cpu"):
        super().__init__(model_id_or_path=model_id_or_path, device=device)

    def get_model_metadata(self) -> Dict[str, Any]:
        data = super().get_model_metadata()
        data["adapter"] = "FineTunedLayaAdapter"
        data["domain"] = "Indian Railways Maintenance Block Operations"
        return data
