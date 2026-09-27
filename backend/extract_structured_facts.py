import json
import os
import sys

from .extract_text import extract_report_content
from .gemini import get_gemini_client
from .structured_facts import extract_structured_facts


def main():
	if len(sys.argv) < 2:
		print("Usage: python -m backend.extract_structured_facts <pdf_path>")
		sys.exit(1)

	pdf_path = sys.argv[1]
	report_pages = extract_report_content(pdf_path)
	structured_facts = extract_structured_facts(report_pages, get_gemini_client())
	report_name = os.path.splitext(os.path.basename(pdf_path))[0]
	output_path = os.path.join("outputs", f"structured_facts_{report_name}.json")
	os.makedirs("outputs", exist_ok=True)
	with open(output_path, "w", encoding="utf-8") as facts_file:
		json.dump(structured_facts, facts_file, indent=2)
	print(f"Structured facts saved to {os.path.abspath(output_path)}")


if __name__ == "__main__":
	main()
