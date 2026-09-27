import json
import os
import sys
from typing import Any

from .gemini import (
    GeminiConfigurationError,
    GeminiDailyLimitError,
    GeminiPermanentError,
    GeminiServiceError,
    get_gemini_client,
    get_remaining_request_budget,
)
from .paper_sections import generate_section
from .section_planner import plan_sections
from .schemas import GeneratedPaperSection, PaperGenerationResult


def generate_paper(facts: dict, client: Any) -> PaperGenerationResult:
    """Generate a partial, review-required paper within the local Gemini budget."""
    verified_by_id = {
        fact["fact_id"]: fact
        for fact in facts.get("facts", [])
        if fact.get("status") == "verified" and fact.get("fact_id")
    }
    planned_sections = plan_sections(facts, client)
    remaining_budget = get_remaining_request_budget()
    generated = []
    skipped = []

    for index, section in enumerate(planned_sections):
        fact_ids = list(section["verified_fact_ids"])
        relevant_facts = [verified_by_id[fact_id] for fact_id in fact_ids if fact_id in verified_by_id]
        if not relevant_facts:
            skipped.append({"section_name": section["section_name"], "reason": "No verified facts support this section.", "verified_fact_ids": fact_ids})
            continue
        if remaining_budget <= 0:
            skipped.extend({"section_name": item["section_name"], "reason": "Local Gemini request budget is exhausted.", "verified_fact_ids": item["verified_fact_ids"]} for item in planned_sections[index:])
            break

        try:
            minimum, maximum = section["word_range"]
            content = generate_section(section["section_name"], relevant_facts, client, minimum, maximum)
            generated.append(GeneratedPaperSection(
                section_name=section["section_name"],
                verified_fact_ids=fact_ids,
                content=content,
            ))
        except (GeminiDailyLimitError, GeminiServiceError, GeminiPermanentError, GeminiConfigurationError) as error:
            safe_reason = "Gemini is busy, please try again later." if isinstance(error, GeminiServiceError) else "Gemini could not generate this section."
            skipped.extend({"section_name": item["section_name"], "reason": safe_reason, "verified_fact_ids": item["verified_fact_ids"]} for item in planned_sections[index:])
            break
        finally:
            remaining_budget = get_remaining_request_budget()

    next_action = "Review generated drafts and verify each sentence against its cited facts."
    if skipped:
        next_action = "Select a skipped section later or wait for the local/provider Gemini budget to reset."
    return PaperGenerationResult(
        generated_sections=generated,
        skipped_sections=skipped,
        remaining_budget=remaining_budget,
        next_action=next_action,
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m backend.generate_paper <facts_json_path>")
        sys.exit(1)

    facts_path = sys.argv[1]
    with open(facts_path, "r", encoding="utf-8") as facts_file:
        facts = json.load(facts_file)

    try:
        result = generate_paper(facts, get_gemini_client())
    except GeminiConfigurationError:
        result = PaperGenerationResult(remaining_budget=get_remaining_request_budget(), skipped_sections=[], next_action="Configure Gemini before generating a draft.")

    facts_name = os.path.splitext(os.path.basename(facts_path))[0]
    output_path = os.path.join("outputs", f"paper_{facts_name}.json")
    os.makedirs("outputs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as paper_file:
        json.dump(result.model_dump(), paper_file, indent=2)

    for section in result.generated_sections:
        print(f"\n{section.section_name}\n{section.content}")
    for section in result.skipped_sections:
        print(f"Skipped {section['section_name']}: {section['reason']}")
    print(f"\nPaper draft saved to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
