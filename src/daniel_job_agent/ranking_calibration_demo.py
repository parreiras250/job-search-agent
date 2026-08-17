"""Demonstração offline dos eixos usados pela decisão final."""

from .models import JobOpportunity
from .profiles import create_daniel_profile
from .rules import evaluate_match


def calibration_cases() -> list[JobOpportunity]:
    base = {
        "source": "Offline fixture",
        "remote": True,
        "brazil_eligible": None,
    }
    cases = (
        ("LATAM Account Executive", "Account Executive", "LATAM", None),
        ("US-only Account Executive", "Account Executive", "United States only", None),
        ("Worldwide Account Executive", "Account Executive", "Worldwide", None),
        ("Europe-only Sales Executive", "Sales Executive", "Europe only", None),
        ("Commission-only Account Executive", "Account Executive", "LATAM", "100% commission only; no base salary"),
        ("Base + commission Account Executive", "Account Executive", "LATAM", "$60k base salary plus commission"),
        ("Maintenance Planner", "Maintenance Planner", "LATAM", None),
        ("Customer Service Representative", "Customer Service Representative", "LATAM", None),
        ("LATAM SDR", "Sales Development Representative", "LATAM", None),
        ("LATAM AE", "Account Executive - LATAM", "Worldwide", None),
        ("Eastern Saudi Arabia AE", "Account Executive - Eastern Saudi Arabia", "Worldwide", None),
        ("SF/Bay Area In-Territory AE", "Account Executive - In-Territory (SF/Bay Area, CA)", "Worldwide", None),
        ("US Market AE", "Account Executive, US Market", "Worldwide", None),
        ("DACH AE", "Account Executive - DACH", "Worldwide", None),
        ("UKI AE", "Account Executive UKI", "Worldwide", None),
        ("ANZ AE", "Account Executive ANZ", "Worldwide", None),
        ("Benelux AE", "Account Executive Benelux", "Worldwide", None),
        ("East AE", "Corporate Account Executive - East", "Worldwide", None),
        ("SLED AE", "Enterprise Account Executive, SLED", "Worldwide", None),
    )
    return [
        JobOpportunity(
            **base,
            company=label,
            role=role,
            location=location,
            description=description,
            job_url=f"https://offline.example/{index}",
        )
        for index, (label, role, location, description) in enumerate(cases, start=1)
    ]


def format_calibration() -> str:
    profile = create_daniel_profile()
    lines = [
        "Company | Role | Career Fit | Eligibility | TZ Fit | Risk | Decision",
        "--- | --- | ---: | --- | --- | --- | ---",
    ]
    for item in calibration_cases():
        result = evaluate_match(item, profile)
        risk = ",".join(value.value for value in result.opportunity_risks) or "NONE"
        lines.append(
            f"{item.company} | {item.role} | {result.score} | "
            f"{result.eligibility.value} | {result.timezone_compatibility.value} | "
            f"{risk} | {result.retention_decision.value}"
        )
    return "\n".join(lines)


def main() -> None:
    print(format_calibration())


if __name__ == "__main__":
    main()
