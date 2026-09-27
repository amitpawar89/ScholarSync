import json
import os
import sys

from backend.extract_text import extract_report_content
from backend.paper_sections import client
from backend.structured_facts import extract_structured_facts


if len(sys.argv) < 2:
	print("Usage: python extract_structured_facts.py <pdf_path>")
	sys.exit(1)

pdf_path = sys.argv[1]
report_pages = extract_report_content(pdf_path)
structured_facts = extract_structured_facts(report_pages, client)

pdf_filename = os.path.basename(pdf_path)
report_name = os.path.splitext(pdf_filename)[0]
output_path = os.path.join("outputs", f"structured_facts_{report_name}.json")
os.makedirs("outputs", exist_ok=True)

with open(output_path, "w", encoding="utf-8") as facts_file:
	json.dump(structured_facts, facts_file, indent=2)

print(f"Structured facts saved to {os.path.abspath(output_path)}")
