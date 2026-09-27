import re

import pymupdf


def clean_text(text):
	# Replace common PDF ligature characters with normal letter sequences.
	ligatures = {
		"ﬀ": "ff",
		"ﬁ": "fi",
		"ﬂ": "fl",
		"ﬃ": "ffi",
		"ﬄ": "ffl",
	}

	for ligature, replacement in ligatures.items():
		text = text.replace(ligature, replacement)

	# Collapse multiple blank lines into one newline.
	text = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n", text)

	# Remove whitespace from the beginning and end of the text.
	return text.strip()


def extract_and_clean_pdf(pdf_path):
	# Open the PDF file provided by the user.
	with pymupdf.open(pdf_path) as pdf_document:
		# Store the cleaned text from every page.
		pages_text = []
		for page_number, page in enumerate(pdf_document, start=1):
			pages_text.append({
				"page_number": page_number,
				"text": clean_text(page.get_text()),
			})

	return pages_text


def extract_report_content(pdf_path):
	"""Extract all page text and block-level source locations without filtering."""
	with pymupdf.open(pdf_path) as pdf_document:
		report_pages = []
		for page_number, page in enumerate(pdf_document, start=1):
			raw_text = page.get_text()
			blocks = []

			for block_number, block in enumerate(page.get_text("blocks"), start=1):
				block_text = block[4]
				if not block_text.strip():
					continue

				blocks.append({
					"block_number": block_number,
					"page_number": page_number,
					"text": clean_text(block_text),
					"bbox": {
						"x0": block[0],
						"y0": block[1],
						"x1": block[2],
						"y1": block[3],
					},
				})

			report_pages.append({
				"page_number": page_number,
				"raw_text": raw_text,
				"text": clean_text(raw_text),
				"blocks": blocks,
			})

	return report_pages


def remove_table_of_contents(pages_text):
	# Remove pages with many leader-dot lines, which usually identify a contents page.
	filtered_pages = []
	for page in pages_text:
		leader_dot_lines = sum(
			bool(re.search(r"\.\s*\.\s*\.", line))
			for line in page["text"].splitlines()
		)

		if leader_dot_lines <= 3:
			filtered_pages.append(page)

	return filtered_pages


def debug_abstract_occurrences(pages_text):
	# Print each occurrence of Abstract with nearby text for temporary debugging.
	for page in pages_text:
		text = page["text"]
		for match in re.finditer(r"\bAbstract\b", text, re.IGNORECASE):
			context_start = max(0, match.start() - 50)
			context_end = min(len(text), match.end() + 50)
			context = text[context_start:context_end].replace("\n", " ")
			print(f"Page {page['page_number']}, context: {context}")


def split_into_sections(pages_text):
	# Join all page text into one document.
	full_text = "\n".join(page["text"] for page in pages_text)

	# Find chapter headings, numbered headings, and common standalone headings.
	heading_pattern = re.compile(
		r"^[ \t]*(?:Chapter\s+\d+[ \t]*\r?\n[ \t]*[^\r\n]+|"
		r"\d+\.\d+[ \t]+[^\r\n]+|"
		r"Abstract|Introduction|Conclusion|References)[ \t]*$",
		re.IGNORECASE | re.MULTILINE,
	)
	matches = list(heading_pattern.finditer(full_text))
	sections = []

	# Keep text before the first heading under Untitled.
	if matches and full_text[:matches[0].start()].strip():
		sections.append({
			"heading": "Untitled",
			"content": full_text[:matches[0].start()].strip(),
		})

	for index, match in enumerate(matches):
		# Use the next heading, or the end of the document, as the content boundary.
		content_end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
		heading = " ".join(match.group(0).split())
		content = full_text[match.end():content_end].strip()

		sections.append({
			"heading": heading,
			"content": content,
		})

	# If there are no headings, keep the complete document under Untitled.
	if not matches and full_text.strip():
		sections.append({
			"heading": "Untitled",
			"content": full_text.strip(),
		})

	return sections


def merge_duplicate_headings(sections):
	# Normalize headings for case-insensitive and whitespace-insensitive comparison.
	def normalize_heading(heading):
		return " ".join(heading.split()).casefold()

	merged_sections = []
	for section in sections:
		if merged_sections and normalize_heading(merged_sections[-1]["heading"]) == normalize_heading(section["heading"]):
			merged_sections[-1]["content"] = "\n\n".join(
				content for content in [merged_sections[-1]["content"], section["content"]] if content
			)
		else:
			merged_sections.append({
				"heading": section["heading"],
				"content": section["content"],
			})

	return merged_sections


if __name__ == "__main__":
	# This simulates a user providing their own report.
	pdf_path = "Sample_Report.pdf"
	pages_text = extract_and_clean_pdf(pdf_path)

	# Temporarily print every Abstract occurrence and its surrounding context.
	debug_abstract_occurrences(pages_text)

	# Remove the table of contents before splitting into sections.
	pages_text = remove_table_of_contents(pages_text)
	sections = split_into_sections(pages_text)
	sections = merge_duplicate_headings(sections)

	# Print the final headings to verify that consecutive duplicates were merged.
	for section in sections:
		print(section["heading"])
