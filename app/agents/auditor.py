AUDITOR_QUESTIONS = {
    "CC6.2": [
        "Provide evidence of periodic user access reviews in the last 90 days.",
        "Show dormant admin accounts and remediation steps."
    ]
}

def probe(control: str) -> list[str]:
    return AUDITOR_QUESTIONS.get(control, ["Provide evidence relevant to this control."])
