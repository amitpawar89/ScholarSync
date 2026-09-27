from pathlib import Path
import shutil
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile

from .extract_text import extract_report_content
from .structured_facts import extract_structured_facts


app = FastAPI(title="ScholarSync Backend")


@app.get("/health")
def health_check():
	return {"status": "ok"}


@app.post("/extract-text")
def extract_text_from_upload(file: UploadFile = File(...)):
	if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
		raise HTTPException(status_code=400, detail="Please upload a PDF file.")

	try:
		with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
			shutil.copyfileobj(file.file, temporary_file)
			temporary_path = temporary_file.name

		pages = extract_report_content(temporary_path)
		return {"pages": pages, "page_count": len(pages)}
	finally:
		if "temporary_path" in locals():
			Path(temporary_path).unlink(missing_ok=True)


@app.post("/structured-facts")
def extract_structured_facts_from_upload(file: UploadFile = File(...)):
	if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
		raise HTTPException(status_code=400, detail="Please upload a PDF file.")

	try:
		with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
			shutil.copyfileobj(file.file, temporary_file)
			temporary_path = temporary_file.name

		report_pages = extract_report_content(temporary_path)
		structured_facts = extract_structured_facts(report_pages, _get_gemini_client())
		return {
			"page_count": len(report_pages),
			"structured_facts": structured_facts,
		}
	finally:
		if "temporary_path" in locals():
			Path(temporary_path).unlink(missing_ok=True)


def _get_gemini_client():
	"""Load the shared Gemini client only when the structured endpoint is used."""
	from .paper_sections import client

	return client


if __name__ == "__main__":
	import uvicorn

	uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
