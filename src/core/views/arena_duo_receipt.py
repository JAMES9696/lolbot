from typing import Optional


def build_arena_duo_receipt(
    *,
    target_name: str,
    target_champion: str,
    partner_name: Optional[str],
    partner_champion: Optional[str],
    placement: Optional[int],
) -> str:
    title = "[RECEIPT] DUO | ARENA"
    line = "+" + "-" * 54 + "+"
    duo = f"{target_name} · {target_champion}"
    if partner_name or partner_champion:
        duo += f"  +  {partner_name or '-'} · {partner_champion or '-'}"
    meta = f"Placement: 第{placement}名" if placement else "Placement: -"
    rows = [
        title,
        line,
        duo,
        meta,
        line,
    ]
    return "\n".join(rows)
