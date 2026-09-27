import json
import os
import sys

from .extract_text import extract_report_content
from .gemini import get_gemini_client
from .structured_facts import extract_structured_facts


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "Sample_Report.pdf"
    pages = extract_report_content(pdf_path)
    facts = extract_structured_facts(pages, get_gemini_client())
    report_name = os.path.splitext(os.path.basename(pdf_path))[0]
    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", f"structured_facts_{report_name}.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(facts, output_file, indent=2)
    print(f"Validated facts saved to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
