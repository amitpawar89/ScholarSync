import re

import pymupdf

from .config import settings


class PdfExtractionError(ValueError):
	"""Raised for invalid, unsupported, or bounded-out PDF documents."""


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


def extract_report_content(pdf_path, max_pages=None, max_text_chars=None):
	"""Extract all page text and block locations without filtering source content."""
	max_pages = settings.max_pages if max_pages is None else max_pages
	max_text_chars = settings.max_text_chars if max_text_chars is None else max_text_chars
	pdf_document = None
	try:
		with open(pdf_path, "rb") as pdf_file:
			pdf_bytes = pdf_file.read()
		pdf_document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
		if pdf_document.needs_pass:
			raise PdfExtractionError("Encrypted PDFs are not supported")
		if len(pdf_document) == 0:
			raise PdfExtractionError("The PDF has no pages")
		if len(pdf_document) > max_pages:
			raise PdfExtractionError(f"The PDF exceeds the {max_pages}-page limit")

		return _extract_open_document(pdf_document, max_text_chars)
	except PdfExtractionError:
		raise
	except Exception as error:
		raise PdfExtractionError("The PDF is malformed or unsupported") from error
	finally:
		if pdf_document is not None:
			pdf_document.close()


def _extract_open_document(pdf_document, max_text_chars):
	"""Extract an already-open, validated document."""
	report_pages = []
	total_text_chars = 0
	for page_number, page in enumerate(pdf_document, start=1):
		raw_text = page.get_text()
		total_text_chars += len(raw_text)
		if total_text_chars > max_text_chars:
			raise PdfExtractionError(f"The extracted text exceeds the {max_text_chars}-character limit")
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

	if not any(page["text"] for page in report_pages):
		raise PdfExtractionError("The PDF contains no extractable text")
	return report_pages
