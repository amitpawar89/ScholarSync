import json

from .gemini import GeminiServiceError, build_generation_config, call_gemini_with_retry
from .schemas import SectionPlanList


def plan_sections(facts, client):
    # Ask Gemini to select only sections supported by the complete facts dictionary.
    prompt = f"""
Based on ONLY the information present in these facts, decide which standard
research-paper sections can be meaningfully written. Consider standard sections
like Introduction, Methodology/Proposed System, Results, Discussion, Conclusion
— but only include a section if there is enough factual information to support it.
If the facts suggest a section beyond these standard ones is relevant (for example,
'Ethical Considerations' if the facts mention data privacy, or 'System Architecture'
if there is strong technical detail), you may include it.

Facts:
{json.dumps(facts, indent=2)}

Do not include a section if there isn't enough factual basis for it.

Return only a JSON list of objects. Each object must contain exactly these keys:
"section_name" (string), "facts_fields_to_use" (list of field names from the
facts dictionary), "word_range" ([min_words, max_words]), and
"writing_instructions" (one sentence describing what the section should cover).
"""

    response = call_gemini_with_retry(
        client,
        "gemini-3.8-flash",
        prompt,
        config=build_generation_config(SectionPlanList.model_json_schema()),
    )
    if response is None:
        return _default_overview(facts)

    response_text = response.text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    elif response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]

    try:
        parsed = json.loads(response_text.strip())
        if isinstance(parsed, list):
            parsed = {"sections": parsed}
        result = SectionPlanList.model_validate(parsed)
        allowed_fields = set(facts)
        if any(field not in allowed_fields for section in result.sections for field in section.facts_fields_to_use):
            raise ValueError("Section plan references an unknown fact field")
        return [section.model_dump() for section in result.sections]
    except (json.JSONDecodeError, ValueError, TypeError, GeminiServiceError):
        return _default_overview(facts)


def _default_overview(facts):
    # Preserve every non-null fact in one safe fallback section.
    non_null_facts = {
        field: value
        for field, value in facts.items()
        if value is not None and value != "" and value != [] and value != {}
    }
    return [{
        "section_name": "Overview",
        "facts_fields_to_use": list(non_null_facts),
        "word_range": [150, 400],
        "writing_instructions": "Summarize the report using the available factual information.",
    }]