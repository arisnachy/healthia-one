from __future__ import annotations


FLEET = (
    ("historia", "Longitudinal history and continuity"),
    ("sentinel", "Deterministic safety and warning-sign review"),
    ("lumen", "Clinical evidence and result interpretation support"),
    ("vita", "Vitals, activity and longitudinal signal context"),
    ("navigator", "Care and resource navigation"),
    ("hereditas", "Family history and hereditary context"),
    ("archivum", "Document and evidence organization"),
    ("medsafe", "Medication evidence and safety context"),
    ("advocate", "Patient goals, questions and follow-through"),
    ("bastion", "Privacy, authorization and boundary review"),
)


def agent_fleet_manifest() -> dict[str, object]:
    return {
        "root": "kira_health",
        "framework": "google_adk",
        "execution": "demand_driven_bounded",
        "subagent_count": len(FLEET),
        "subagents": [
            {"name": name, "role": role, "execution_authority": "recommendation_only"}
            for name, role in FLEET
        ],
        "external_mutation_authority": "one_safety_kernel_only",
    }
