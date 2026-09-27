import json
import os
import sys

from backend.paper_sections import client, generate_section
from backend.section_planner import plan_sections


# Require the path to an extracted facts JSON file from the command line.
if len(sys.argv) < 2:
	print("Usage: python generate_paper.py <facts_json_path>")
	sys.exit(1)

facts_path = sys.argv[1]

# Load the extracted facts.
with open(facts_path, "r", encoding="utf-8") as facts_file:
	facts = json.load(facts_file)

# Generate only the sections supported by the available facts.
paper_sections = {}
for section in plan_sections(facts, client):
	relevant_facts = {
		field: facts.get(field)
		for field in section["facts_fields_to_use"]
	}
	min_words, max_words = section["word_range"]
	paper_sections[section["section_name"]] = generate_section(
		section["section_name"],
		section["writing_instructions"],
		relevant_facts,
		client,
		min_words,
		max_words,
	)

	print(f"\n{section['section_name']}\n")
	print(paper_sections[section["section_name"]])

# Save the generated sections using the facts file's name.
facts_filename = os.path.basename(facts_path)
facts_name = os.path.splitext(facts_filename)[0]
output_path = os.path.join("outputs", f"paper_{facts_name}.json")
os.makedirs("outputs", exist_ok=True)
with open(output_path, "w", encoding="utf-8") as paper_file:
	json.dump(paper_sections, paper_file, indent=2)

print(f"\nPaper sections saved to {os.path.abspath(output_path)}")
