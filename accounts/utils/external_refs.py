from django.utils.timezone import now


def generate_external_ref(*, client_id: int, fund_strategy: str, flow_date) -> str:
    """
    Generate a human-readable, deterministic external_ref.
    """
    date_str = flow_date.strftime("%Y%m%d")
    return f"MANUAL-{client_id}-{fund_strategy}-{date_str}"
