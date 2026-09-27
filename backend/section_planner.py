import json
from typing import Any

from pydantic import ValidationError

from .gemini import GeminiDailyLimitError, GeminiPermanentError, GeminiServiceError, build_generation_config, call_gemini_with_retry
from .schemas import SectionPlan, SectionPlanList


def _fallback() -> list[dict]:
    return []


def _parse_plan(response: Any, verified_fact_ids: set[str]) -> list[dict]:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, SectionPlanList):
        plan = parsed
    elif isinstance(parsed, dict):
        plan = SectionPlanList.model_validate(parsed)
    else:
        plan = SectionPlanList.model_validate(json.loads(getattr(response, "text", "")))

    validated = []
    for item in plan.sections:
        if not item.verified_fact_ids:
            continue
        if any(fact_id not in verified_fact_ids for fact_id in item.verified_fact_ids):
            continue
        validated.append(item.model_dump())
    return validated


def plan_sections(facts: dict, client: Any) -> list[dict]:
    verified_facts = [fact for fact in facts.get("facts", []) if fact.get("status") == "verified" and fact.get("fact_id")]
    verified_fact_ids = {fact["fact_id"] for fact in verified_facts}
    if not verified_facts:
        return _fallback()

    prompt = f"""
Use ONLY the verified report facts below to propose research-paper sections.
Section titles must be determined by the report and may be any appropriate title.
Do not force standard sections. Do not include a section without enough verified
facts. Each section must reference only verified_fact_ids shown below.

Return exactly this structured JSON object and no other keys:
{{"sections": [{{"section_name": "...", "verified_fact_ids": ["fact_0001"], "word_range": [150, 400]}}]}}

Do not write prose or instructions. Word ranges must be between 20 and 2000.
<VERIFIED_FACTS>
{json.dumps(verified_facts, indent=2)}
</VERIFIED_FACTS>
"""
    try:
        response = call_gemini_with_retry(
            client, "gemini-3.8-flash", prompt,
            config=build_generation_config(SectionPlanList.model_json_schema()),
        )
        return _parse_plan(response, verified_fact_ids)
    except (GeminiDailyLimitError, GeminiPermanentError, GeminiServiceError, ValidationError, json.JSONDecodeError, TypeError, ValueError):
        return _fallback()
