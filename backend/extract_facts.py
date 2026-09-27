import json
import os
import sys
import time

from dotenv import load_dotenv
from google import genai

from backend.extract_text import (
	extract_and_clean_pdf,
	remove_table_of_contents,
)


# Load the Gemini API key from the .env file and create a client.
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
	raise RuntimeError("GEMINI_API_KEY is not set in the .env file")

client = genai.Client(api_key=api_key)


def call_gemini_with_retry(client, model, prompt):
	# Retry up to five times with exponential backoff between attempts.
	max_retries = 5
	wait_seconds = 5
	for attempt in range(1, max_retries + 1):
		try:
			return client.models.generate_content(model=model, contents=prompt)
		except Exception:
			if attempt < max_retries:
				print(
					f"Attempt {attempt} failed, waiting {wait_seconds} seconds before retrying..."
				)
				time.sleep(wait_seconds)
				wait_seconds *= 2

	return None


def extract_facts_from_full_report(combined_report_text, client):
	# Build one prompt that searches the entire report for every requested field.
	prompt = f"""
Extract the following fields by looking at the ENTIRE report below.
A field may be mentioned in any section, not necessarily where you'd expect it.
Only use information that is explicitly written somewhere in this report.
Do not add, guess, or infer anything not stated in the text. If truly not found anywhere, use null.

The "technologies_used" field must be a dictionary grouped by categories based
only on categories explicitly written in the report, such as "Web Development",
"Database", "AI/ML", or "System Architecture", or similar clear categories.
If the report does not organize technologies into categories, use one category
called "General". For example: {{"Frontend": ["React.js", "Tailwind CSS"],
"Backend": ["Node.js"], "Database": ["PostgreSQL", "Redis"],
"AI/ML": ["LSTM", "Scikit-learn"]}}.

Return a strict JSON object with exactly these keys:
"problem_statement", "objectives", "technologies_used", "dataset_or_components", "results", "not_found_but_expected"

The "technologies_used" value must be an object whose keys are category names
and whose values are lists of technologies, or null if no technologies are
mentioned.

The "not_found_but_expected" field must list which of the other fields were not
found anywhere in the report.

Entire report:
{combined_report_text}
"""

	# Ask Gemini to return the extracted facts as JSON, with retries for API failures.
	response = call_gemini_with_retry(client, "gemini-3.8-flash", prompt)
	if response is None:
		return {"error": "Gemini API unavailable after 3 retries"}

	# Remove optional Markdown JSON fences before parsing the response.
	response_text = response.text.strip()
	if response_text.startswith("```json"):
		response_text = response_text[7:]
	elif response_text.startswith("```"):
		response_text = response_text[3:]
	if response_text.endswith("```"):
		response_text = response_text[:-3]

	try:
		return json.loads(response_text.strip())
	except json.JSONDecodeError:
		return {
			"error": "could not parse",
			"raw_response": response.text,
		}


def generate_missing_info_questions(facts):
	# Map each expected fact field to a friendly question for the student.
	question_templates = {
		"results": "We couldn't find your project's results or outcomes in the report. Could you share them?",
		"technologies_used": "We couldn't find the technologies/tools used in your project. Could you list them?",
		"problem_statement": "We couldn't find a clear problem statement. Could you describe the problem your project solves?",
		"objectives": "We couldn't find clear objectives. Could you list your project's objectives?",
		"dataset_or_components": "We couldn't find the dataset or components used. Could you describe them?",
	}
	questions = []

	for field in facts.get("not_found_but_expected", []):
		if field in question_templates:
			questions.append({
				"field": field,
				"question": question_templates[field],
			})

	return questions


# Get the PDF path from the command line, or use the sample report by default.
if len(sys.argv) > 1:
	pdf_path = sys.argv[1]
else:
	pdf_path = "Sample_Report.pdf"
	print("No PDF path provided. Using Sample_Report.pdf")

# Extract and clean every page in the report.
pages_text = extract_and_clean_pdf(pdf_path)
cleaned_pages = remove_table_of_contents(pages_text)

# Combine every retained page directly, without heading detection or filtering.
combined_report_text = "\n\n".join(
	page["text"]
	for page in cleaned_pages
)

# Extract facts with one Gemini request for the complete report.
all_facts = extract_facts_from_full_report(combined_report_text, client)

# Stop without saving if the AI service could not provide facts.
if "error" in all_facts:
	print("Could not extract facts because the AI service was unavailable. Please try again in a few minutes.")
	sys.exit(1)

# Build an output filename from the input PDF's name.
pdf_filename = os.path.basename(pdf_path)
report_name = os.path.splitext(pdf_filename)[0]
output_filename = f"extracted_facts_{report_name}.json"
os.makedirs("outputs", exist_ok=True)
output_path = os.path.join("outputs", output_filename)

# Save all extracted facts to the outputs folder.
with open(output_path, "w", encoding="utf-8") as facts_file:
	json.dump(all_facts, facts_file, indent=2)

print(f"Done! Facts saved to {os.path.abspath(output_path)}")

# Load the saved facts and print questions for missing information.
with open(output_path, "r", encoding="utf-8") as facts_file:
	saved_facts = json.load(facts_file)

missing_info_questions = generate_missing_info_questions(saved_facts)
for item in missing_info_questions:
	print(f"{item['field']}: {item['question']}")
