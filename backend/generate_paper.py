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
    for section in plan_sections(facts, client):
        relevant_facts = {field: facts.get(field) for field in section["facts_fields_to_use"]}
        min_words, max_words = section["word_range"]
        content = generate_section(
            section["section_name"],
            section["writing_instructions"],
            relevant_facts,
            client,
            min_words,
            max_words,
        )
        paper_sections[section["section_name"]] = content
        print(f"\n{section['section_name']}\n{content}")

    facts_name = os.path.splitext(os.path.basename(facts_path))[0]
    output_path = os.path.join("outputs", f"paper_{facts_name}.json")
    os.makedirs("outputs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as paper_file:
        json.dump(paper_sections, paper_file, indent=2)
    print(f"\nPaper sections saved to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
