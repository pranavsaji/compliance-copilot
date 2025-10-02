CROSSWALK = {
    "SOC2:CC6.2": ["ISO27001:A.9.2", "HIPAA:164.308(a)(4)"],
    "SOC2:CC6.1": ["ISO27001:A.10.1", "HIPAA:164.312(a)(2)"],
}

def map_controls(control_ids: list[str]) -> dict[str, list[str]]:
    out = {}
    for cid in control_ids:
        if cid in CROSSWALK:
            out[cid] = CROSSWALK[cid]
    return out
