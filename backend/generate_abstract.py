import json
import os
import sys

from backend.paper_sections import call_gemini_with_retry, client, generate_section
from backend.section_planner import plan_sections


def generate_abstract(facts, client):
	# Include only the fact fields that may support the abstract.
	abstract_facts = {
		field: facts.get(field)
		for field in (
			"problem_statement",
			"objectives",
			"technologies_used",
			"dataset_or_components",
			"results",
		)
	}

	# Build a prompt that restricts the abstract to explicitly extracted facts.
	prompt = f"""
Write a professional research-paper-style Abstract of 150-250 words using ONLY the facts below.

Facts:
{json.dumps(abstract_facts, indent=2)}

Do not add any claim, number, or detail that is not present in the given facts.
If 'results' is null, do not mention any specific outcome or performance number —
you may only say that implementation/evaluation is in progress, or omit results entirely.

Return plain text only: just the abstract paragraph, without JSON, Markdown, a title, or commentary.
"""

	# Ask Gemini to generate the abstract with retry handling.
	response = call_gemini_with_retry(client, "gemini-3.8-flash", prompt)
	if response is None:
		return "Could not generate the abstract because the AI service was unavailable."

	return response.text.strip()

def determine_available_sections(facts):
	# Treat None, empty strings, lists, and dictionaries as unavailable values.
	def has_value(field):
		value = facts.get(field)
		return value is not None and value != "" and value != [] and value != {}

	available_sections = []

	if has_value("problem_statement"):
		introduction_fields = ["problem_statement"]
		if has_value("objectives"):
			introduction_fields.append("objectives")
		available_sections.append({
			"name": "Introduction",
			"facts_needed": introduction_fields,
			"instructions": "Write 250-400 words to introduce the problem, explain its importance, and briefly state the proposed solution.",
		})

	methodology_fields = [
		field
		for field in ("technologies_used", "dataset_or_components")
		if has_value(field)
	]
	if methodology_fields:
		available_sections.append({
			"name": "Methodology",
			"facts_needed": methodology_fields,
			"instructions": "Write 200-350 words describing the system's technical approach and components used.",
		})

	if has_value("results"):
		available_sections.append({
			"name": "Results",
			"facts_needed": ["results"],
			"instructions": "Write 150-250 words describing the reported results or outcomes without inventing any additional outcomes, statistics, or performance numbers.",
		})

	if has_value("problem_statement"):
		conclusion_fields = ["problem_statement"]
		for field in ("objectives", "results"):
			if has_value(field):
				conclusion_fields.append(field)
		available_sections.append({
			"name": "Conclusion",
			"facts_needed": conclusion_fields,
			"instructions": "Write 150-250 words summarizing what was achieved or proposed, without inventing outcomes.",
		})

	return available_sections


if __name__ == "__main__":
	# Get the facts JSON path from the command line.
	if len(sys.argv) < 2:
		print("Usage: python generate_abstract.py <facts_json_path>")
		sys.exit(1)

	facts_path = sys.argv[1]

	# Load the facts and ask Gemini to plan the available paper sections.
	with open(facts_path, "r", encoding="utf-8") as facts_file:
		facts = json.load(facts_file)

	planned_sections = plan_sections(facts, client)

	# Print the plan in a readable format.
	for section in planned_sections:
		print(f"\n{section['section_name']}")
		print(f"Word range: {section['word_range']}")
		print(f"Instructions: {section['writing_instructions']}")

	# Save the plan using the facts file's name.
	facts_filename = os.path.basename(facts_path)
	facts_name = os.path.splitext(facts_filename)[0]
	output_path = os.path.join("outputs", f"plan_{facts_name}.json")
	os.makedirs("outputs", exist_ok=True)
	with open(output_path, "w", encoding="utf-8") as plan_file:
		json.dump(planned_sections, plan_file, indent=2)

	print(f"\nPlan saved to {os.path.abspath(output_path)}")
