import json
import os
import sys

from .gemini import get_gemini_client
from .paper_sections import generate_section


def generate_abstract(facts: dict, client) -> str:
    fields = {field: facts.get(field) for field in ("problem_statement", "objectives", "technologies_used", "dataset_or_components", "results")}
    instructions = "Write a professional research-paper abstract of 150-250 words. If results are null, omit outcomes or state only that evaluation is in progress."
    return generate_section("Abstract", instructions, fields, client, 150, 250)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m backend.generate_abstract <facts_json_path>")
        sys.exit(1)
    facts_path = sys.argv[1]
    with open(facts_path, "r", encoding="utf-8") as facts_file:
        facts = json.load(facts_file)
    abstract = generate_abstract(facts, get_gemini_client())
    facts_name = os.path.splitext(os.path.basename(facts_path))[0]
    output_path = os.path.join("outputs", f"abstract_{facts_name}.txt")
    os.makedirs("outputs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as abstract_file:
        abstract_file.write(abstract + "\n")
    print(f"Abstract saved to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
