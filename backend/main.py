from pathlib import Path
import asyncio
import tempfile
import shutil

from fastapi import FastAPI, File, HTTPException, UploadFile

from .config import settings
from .extract_text import PdfExtractionError, extract_report_content
from .gemini import GeminiConfigurationError, get_gemini_client
from .structured_facts import extract_structured_facts


app = FastAPI(title="ScholarSync Backend")


@app.get("/health")
def health_check():
	return {"status": "ok"}


async def _save_pdf(file: UploadFile) -> str:
	if not file.filename:
		raise HTTPException(status_code=400, detail="A PDF file is required.")
	temporary_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
	temporary_path = temporary_file.name
	temporary_file.close()
	try:
		if await file.read(5) != b"%PDF-":
			raise HTTPException(status_code=400, detail="The uploaded file is not a PDF.")
		await file.seek(0)
		total = 0
		while chunk := await file.read(1024 * 1024):
			total += len(chunk)
			if total > settings.max_upload_bytes:
				raise HTTPException(status_code=413, detail="The uploaded PDF exceeds the size limit.")
			with open(temporary_path, "ab") as output_file:
				output_file.write(chunk)
		return temporary_path
	except Exception:
		Path(temporary_path).unlink(missing_ok=True)
		raise
	finally:
		await file.close()


@app.post("/extract-text")
async def extract_text_from_upload(file: UploadFile = File(...)):
	try:
		temporary_path = await _save_pdf(file)
		try:
			pages = extract_report_content(temporary_path)
			return {"pages": pages, "page_count": len(pages)}
		finally:
			Path(temporary_path).unlink(missing_ok=True)
	except PdfExtractionError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/structured-facts")
async def extract_structured_facts_from_upload(file: UploadFile = File(...)):
	try:
		temporary_path = await _save_pdf(file)
		try:
			report_pages = extract_report_content(temporary_path)
			try:
				gemini_client = get_gemini_client()
			except GeminiConfigurationError as error:
				raise HTTPException(status_code=503, detail="Gemini is not configured.") from error
			result = await asyncio.to_thread(extract_structured_facts, report_pages, gemini_client)
			if "error" in result:
				raise HTTPException(status_code=503, detail=result["error"])
			return {"page_count": len(report_pages), "structured_facts": result}
		finally:
			Path(temporary_path).unlink(missing_ok=True)
	except PdfExtractionError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error


if __name__ == "__main__":
	import uvicorn

	uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
