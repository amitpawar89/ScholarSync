import json

from backend.paper_sections import call_gemini_with_retry


FACT_FIELDS = (
	"project_type",
	"category",
	"claim",
	"evidence",
	"page_number",
	"block_number",
	"status",
)


def build_report_source(report_pages):
	"""Create a traceable text representation without dropping report content."""
	source_parts = []
	for page in report_pages:
		for block in page.get("blocks", []):
			source_parts.append(
				f"[Page {block['page_number']}, Block {block['block_number']}]\n"
				f"{block['text']}"
			)

	return "\n\n".join(source_parts)


def extract_structured_facts(report_pages, client):
	"""Extract explicit, source-linked facts from all report blocks."""
	report_source = build_report_source(report_pages)
	prompt = f"""
Extract ALL explicit information and points from the report source below.

Do not summarize away details. Do not add, guess, infer, or correct anything.
Every extracted fact must be directly supported by the report source.
Preserve numbers, names, technologies, components, methods, datasets, results,
limitations, assumptions, and future work when they are explicitly present.

Return a strict JSON object with exactly these keys:
"project_type": a string or null,
"facts": a list of objects,
"missing_or_unclear": a list of objects.

Each object in "facts" must contain exactly these keys:
"category", "claim", "evidence", "page_number", "block_number", "status".
Use "verified" for status only when the claim is explicitly supported.
The "evidence" value must quote the supporting report text.

Each object in "missing_or_unclear" must contain:
"field", "reason", "question".
Only include information that would be useful for a research paper but is not
clearly present. Do not treat missing information as an extracted fact.

Report source:
{report_source}
"""

	response = call_gemini_with_retry(client, "gemini-3.8-flash", prompt)
	if response is None:
		return {"error": "Gemini API unavailable after retries"}

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
			"error": "could not parse structured facts",
			"raw_response": response.text,
		}
