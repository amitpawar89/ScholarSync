from pathlib import Path
import asyncio
import tempfile
import shutil

from fastapi import FastAPI, File, HTTPException, UploadFile

from .config import settings
from .extract_text import PdfExtractionError, extract_report_content
from .gemini import (
	GeminiConfigurationError,
	GeminiDailyLimitError,
	GeminiPermanentError,
	GeminiServiceError,
	get_gemini_client,
	get_remaining_request_budget,
)
from .paper_sections import generate_section
from .schemas import GeneratedPaperSection, PaperGenerationResult
from .section_planner import plan_sections
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
			if sum(len(page["text"]) for page in report_pages) > settings.structured_max_text_chars:
				raise HTTPException(status_code=413, detail="This report is too large for free-tier structured extraction. Please upload a smaller report.")
			try:
				gemini_client = get_gemini_client()
			except GeminiConfigurationError as error:
				raise HTTPException(status_code=503, detail="Gemini is not configured.") from error
			try:
				result = await asyncio.to_thread(extract_structured_facts, report_pages, gemini_client)
			except GeminiDailyLimitError as error:
				raise HTTPException(status_code=429, detail="The local free-tier Gemini request limit has been reached. Please try again later.") from error
			except GeminiServiceError as error:
				raise HTTPException(status_code=503, detail="Gemini is busy, please try again later.") from error
			except GeminiPermanentError as error:
				raise HTTPException(status_code=502, detail="Gemini rejected the request. Check the server configuration or report format.") from error
			if "error" in result:
				status = 413 if "too large" in result["error"].lower() or "smaller report" in result["error"].lower() else 502
				raise HTTPException(status_code=status, detail=result["error"])
			return {"page_count": len(report_pages), "structured_facts": result}
		finally:
			Path(temporary_path).unlink(missing_ok=True)
	except PdfExtractionError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/generate-paper", response_model=PaperGenerationResult)
async def generate_paper_from_upload(file: UploadFile = File(...)):
	try:
		temporary_path = await _save_pdf(file)
		try:
			report_pages = extract_report_content(temporary_path)
			if sum(len(page["text"]) for page in report_pages) > settings.structured_max_text_chars:
				raise HTTPException(
					status_code=413,
					detail="This report is too large for free-tier structured extraction. Please upload a smaller report."
				)
			try:
				gemini_client = get_gemini_client()
			except GeminiConfigurationError as error:
				raise HTTPException(status_code=503, detail="Gemini is not configured.") from error
			try:
				facts_result = await asyncio.to_thread(extract_structured_facts, report_pages, gemini_client)
			except GeminiDailyLimitError as error:
				raise HTTPException(
					status_code=429,
					detail="The local free-tier Gemini request limit has been reached. Please try again later."
				) from error
			except GeminiServiceError as error:
				raise HTTPException(status_code=503, detail="Gemini is busy, please try again later.") from error
			except GeminiPermanentError as error:
				raise HTTPException(
					status_code=502,
					detail="Gemini rejected the request. Check the server configuration or report format."
				) from error

			if "error" in facts_result:
				status = 413 if "too large" in facts_result["error"].lower() or "smaller report" in facts_result["error"].lower() else 502
				raise HTTPException(status_code=status, detail=facts_result["error"])

			verified_facts = [
				fact for fact in facts_result.get("facts", [])
				if fact.get("status") == "verified" and fact.get("fact_id")
			]

			clean_missing = []
			for item in facts_result.get("missing_or_unclear", []):
				if hasattr(item, "model_dump"):
					clean_missing.append(item.model_dump())
				elif isinstance(item, dict):
					clean_missing.append(item)
				else:
					clean_missing.append({"question": str(item)})

			questions = [
				item["question"] for item in clean_missing
				if isinstance(item, dict) and "question" in item
			]

			if not verified_facts:
				return PaperGenerationResult(
					status="draft_requires_review",
					generated_sections=[],
					skipped_sections=[],
					remaining_budget=get_remaining_request_budget(),
					next_action="No sections could be generated because no verified facts were found. Provide missing information and try again.",
					missing_or_unclear=clean_missing,
					questions=questions,
				)

			verified_by_id = {fact["fact_id"]: fact for fact in verified_facts}
			planned_sections = await asyncio.to_thread(plan_sections, facts_result, gemini_client)

			remaining_budget = get_remaining_request_budget()
			generated_sections: list[GeneratedPaperSection] = []
			skipped_sections: list[dict] = []

			for index, section in enumerate(planned_sections):
				fact_ids = list(section.get("verified_fact_ids", []))
				relevant_facts = [verified_by_id[fid] for fid in fact_ids if fid in verified_by_id]
				if not relevant_facts:
					skipped_sections.append({
						"section_name": section.get("section_name", ""),
						"reason": "No verified facts support this section.",
						"verified_fact_ids": fact_ids,
					})
					continue

				if remaining_budget <= 0:
					for item in planned_sections[index:]:
						skipped_sections.append({
							"section_name": item.get("section_name", ""),
							"reason": "Local Gemini request budget is exhausted.",
							"verified_fact_ids": list(item.get("verified_fact_ids", [])),
						})
					break

				try:
					word_range = section.get("word_range", (150, 400))
					min_words, max_words = word_range[0], word_range[1]
					content = await asyncio.to_thread(
						generate_section,
						section["section_name"],
						relevant_facts,
						gemini_client,
						min_words,
						max_words,
					)
					generated_sections.append(
						GeneratedPaperSection(
							section_name=section["section_name"],
							verified_fact_ids=fact_ids,
							content=content,
							status="draft_requires_review",
						)
					)
				except (GeminiDailyLimitError, GeminiServiceError, GeminiPermanentError, GeminiConfigurationError) as error:
					safe_reason = "Gemini is busy, please try again later." if isinstance(error, GeminiServiceError) else "Gemini could not generate this section."
					for item in planned_sections[index:]:
						skipped_sections.append({
							"section_name": item.get("section_name", ""),
							"reason": safe_reason,
							"verified_fact_ids": list(item.get("verified_fact_ids", [])),
						})
					break
				finally:
					remaining_budget = get_remaining_request_budget()

			return PaperGenerationResult(
				status="draft_requires_review",
				generated_sections=generated_sections,
				skipped_sections=skipped_sections,
				remaining_budget=remaining_budget,
				next_action="Review the draft sections below." if generated_sections else "Provide missing information and try again.",
				missing_or_unclear=clean_missing,
				questions=questions,
			)
		finally:
			Path(temporary_path).unlink(missing_ok=True)
	except PdfExtractionError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error


if __name__ == "__main__":
	import uvicorn

	uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
