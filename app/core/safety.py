from app.domain.constants import SAFETY_DISCLAIMER


def verify_advisory_compliance(actor_role: str, action: str) -> None:
    """Enforces safety guardrails: AI or unauthorized agents cannot directly execute blocks."""
    allowed_roles = ["Section Controller", "Chief Controller", "Senior Divisional Operations Manager", "Station Master"]
    if actor_role not in allowed_roles:
        raise PermissionError(
            f"Advisory Rule Violation: Action '{action}' requires approval by authorized railway personnel. "
            f"Role '{actor_role}' is not permitted."
        )


def get_safety_headers() -> dict:
    return {
        "X-RailSync-Advisory": SAFETY_DISCLAIMER,
        "X-RailSync-Compliance": "G&SR Southern Railway Rule 4.08",
    }
