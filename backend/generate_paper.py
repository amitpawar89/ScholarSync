import json
import os
import sys

from .gemini import get_gemini_client
from .paper_sections import generate_section
from .section_planner import plan_sections


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m backend.generate_paper <facts_json_path>")
        sys.exit(1)

    facts_path = sys.argv[1]
    with open(facts_path, "r", encoding="utf-8") as facts_file:
        facts = json.load(facts_file)

    client = get_gemini_client()
    paper_sections = {}
    verified_by_id = {
        fact["fact_id"]: fact
        for fact in facts.get("facts", [])
        if fact.get("status") == "verified" and fact.get("fact_id")
    }
    planned_sections = plan_sections(facts, client)
    for section in planned_sections:
        relevant_facts = [verified_by_id[fact_id] for fact_id in section["verified_fact_ids"] if fact_id in verified_by_id]
        if not relevant_facts:
            continue
        min_words, max_words = section["word_range"]
        content = generate_section(
            section["section_name"],
            relevant_facts,
            client,
            min_words,
            max_words,
        )
        paper_sections[section["section_name"]] = content
        print(f"\n{section['section_name']}\n{content}")

    for item in facts.get("missing_or_unclear", []):
        print(f"Missing information: {item['question']}")

    facts_name = os.path.splitext(os.path.basename(facts_path))[0]
    output_path = os.path.join("outputs", f"paper_{facts_name}.json")
    os.makedirs("outputs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as paper_file:
        json.dump(paper_sections, paper_file, indent=2)
    print(f"\nPaper sections saved to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
