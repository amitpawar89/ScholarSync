import io
import importlib
import json
import sys
from types import SimpleNamespace

import pymupdf
from fastapi.testclient import TestClient

from backend import main
from backend.gemini import get_gemini_client
from backend.schemas import StructuredFactsResponse
from backend.section_planner import plan_sections
from backend.structured_facts import validate_structured_facts


def make_pdf(text="A report fact."):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_health_works_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_gemini_client.cache_clear()
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ai_endpoint_returns_503_without_key(monkeypatch):
    from backend.gemini import GeminiConfigurationError
    monkeypatch.setattr(main, "get_gemini_client", lambda: (_ for _ in ()).throw(GeminiConfigurationError("missing")))
    response = TestClient(main.app).post(
        "/structured-facts",
        files={"file": ("report.pdf", make_pdf(), "application/pdf")},
    )
    assert response.status_code == 503


def test_renamed_non_pdf_is_rejected():
    response = TestClient(main.app).post(
        "/extract-text",
        files={"file": ("report.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_malformed_pdf_is_rejected():
    response = TestClient(main.app).post(
        "/extract-text",
        files={"file": ("report.pdf", b"%PDF-1.7\ninvalid", "application/pdf")},
    )
    assert response.status_code == 400


def test_empty_pdf_is_rejected():
    document = pymupdf.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    response = TestClient(main.app).post(
        "/extract-text",
        files={"file": ("report.pdf", data, "application/pdf")},
    )
    assert response.status_code == 400


def test_oversized_upload_is_rejected(monkeypatch):
    small_limits = SimpleNamespace(max_upload_bytes=10, max_pages=100, max_text_chars=1000000)
    monkeypatch.setattr(main, "settings", small_limits)
    response = TestClient(main.app).post(
        "/extract-text",
        files={"file": ("report.pdf", make_pdf("long report"), "application/pdf")},
    )
    assert response.status_code == 413


def test_matching_evidence_becomes_verified():
    pages = [{"page_number": 2, "blocks": [{"page_number": 2, "block_number": 1, "text": "PostgreSQL is used."}]}]
    result = StructuredFactsResponse.model_validate({
        "project_type": "software",
        "facts": [{
            "category": "technology",
            "claim": "PostgreSQL is used.",
            "evidence": "PostgreSQL is used.",
            "page_number": 2,
            "block_number": 1,
            "status": "unverified",
        }],
        "missing_or_unclear": [],
    })
    checked = validate_structured_facts(result, pages)
    assert checked.facts[0].status == "verified"
    assert checked.facts[0].fact_id == "fact_0001"


def test_mismatched_evidence_is_not_verified():
    pages = [{"page_number": 2, "blocks": [{"page_number": 2, "block_number": 1, "text": "Actual evidence."}]}]
    result = StructuredFactsResponse.model_validate({
        "project_type": "software",
        "facts": [{
            "category": "claim",
            "claim": "Unsupported claim",
            "evidence": "Missing evidence",
            "page_number": 2,
            "block_number": 1,
            "status": "verified",
        }],
        "missing_or_unclear": [],
    })
    checked = validate_structured_facts(result, pages)
    assert checked.facts == []
    assert checked.missing_or_unclear[0].field == "unverified_fact"


def test_unrelated_claim_with_real_evidence_is_not_verified():
    pages = [{"page_number": 1, "blocks": [{"page_number": 1, "block_number": 1, "text": "PostgreSQL is used."}]}]
    result = StructuredFactsResponse.model_validate({
        "facts": [{"category": "technology", "claim": "The system uses MongoDB.", "evidence": "PostgreSQL is used.", "page_number": 1, "block_number": 1, "status": "verified"}],
        "missing_or_unclear": [],
    })
    checked = validate_structured_facts(result, pages)
    assert checked.facts == []
    assert "MongoDB" in checked.missing_or_unclear[0].question


def test_project_type_without_source_evidence_is_not_verified():
    result = StructuredFactsResponse.model_validate({"project_type": "machine_learning", "facts": [], "missing_or_unclear": []})
    checked = validate_structured_facts(result, [{"page_number": 1, "blocks": []}])
    assert checked.project_type is None
    assert checked.missing_or_unclear[0].field == "project_type"


def test_invalid_structured_json_is_safe(monkeypatch):
    from backend import structured_facts

    monkeypatch.setattr(structured_facts, "call_gemini_with_retry", lambda *args, **kwargs: SimpleNamespace(text="not json"))
    result = structured_facts.extract_structured_facts([], object())
    assert result["error"] == "invalid structured facts response"


def test_invalid_section_plan_falls_back(monkeypatch):
    import backend.section_planner as planner

    monkeypatch.setattr(planner, "call_gemini_with_retry", lambda *args, **kwargs: SimpleNamespace(text='[{"section_name":"x"}]'))
    result = plan_sections({"facts": [{"fact_id": "fact_0001", "status": "verified", "claim": "known"}]}, object())
    assert result == []


def test_dynamic_section_plan_uses_only_verified_fact_ids(monkeypatch):
    import backend.section_planner as planner

    response = SimpleNamespace(parsed={"sections": [{"section_name": "System Architecture", "verified_fact_ids": ["fact_0001"], "word_range": [200, 300]}]})
    monkeypatch.setattr(planner, "call_gemini_with_retry", lambda *args, **kwargs: response)
    result = plan_sections({"facts": [{"fact_id": "fact_0001", "status": "verified", "claim": "Architecture"}]}, object())
    assert result == [{"section_name": "System Architecture", "verified_fact_ids": ["fact_0001"], "word_range": (200, 300)}]


def test_permanent_gemini_error_is_not_busy(monkeypatch):
    import backend.gemini as gemini
    gemini._daily_request_count = 0
    monkeypatch.setattr(gemini.time, "sleep", lambda _: None)
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("401 UNAUTHENTICATED"))))
    with __import__("pytest").raises(gemini.GeminiPermanentError):
        gemini.call_gemini_with_retry(client, "model", "prompt")


def test_transient_failure_then_api_status(monkeypatch):
    import backend.gemini as gemini
    gemini._daily_request_count = 0
    monkeypatch.setattr(gemini.time, "sleep", lambda _: None)
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("503 UNAVAILABLE"))))
    with __import__("pytest").raises(gemini.GeminiServiceError, match="Gemini is busy"):
        gemini.call_gemini_with_retry(client, "model", "prompt")


def test_permanent_gemini_error_maps_to_502(monkeypatch):
    from backend.gemini import GeminiPermanentError

    monkeypatch.setattr(main, "get_gemini_client", lambda: object())
    monkeypatch.setattr(main, "extract_structured_facts", lambda *args: (_ for _ in ()).throw(GeminiPermanentError("rejected")))
    response = TestClient(main.app).post("/structured-facts", files={"file": ("report.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 502
    assert response.json()["detail"] == "Gemini rejected the request. Check the server configuration or report format."


def test_daily_limit_maps_to_429(monkeypatch):
    from backend.gemini import GeminiDailyLimitError

    monkeypatch.setattr(main, "get_gemini_client", lambda: object())
    monkeypatch.setattr(main, "extract_structured_facts", lambda *args: (_ for _ in ()).throw(GeminiDailyLimitError("limit")))
    response = TestClient(main.app).post("/structured-facts", files={"file": ("report.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 429


def test_structured_endpoint_rejects_large_ai_input_before_client(monkeypatch):
    monkeypatch.setattr(main, "settings", SimpleNamespace(max_upload_bytes=1000000, max_pages=100, max_text_chars=1000000, structured_max_text_chars=1))
    monkeypatch.setattr(main, "get_gemini_client", lambda: (_ for _ in ()).throw(AssertionError("client called")))
    response = TestClient(main.app).post("/structured-facts", files={"file": ("report.pdf", make_pdf("report text"), "application/pdf")})
    assert response.status_code == 413


def test_valid_mocked_structured_response_returns_verified_fact(monkeypatch):
    from backend import main as api

    monkeypatch.setattr(api, "get_gemini_client", lambda: object())
    monkeypatch.setattr(api, "extract_structured_facts", lambda *args: {
        "project_type": None,
        "facts": [{
            "fact_id": "fact_0001",
            "category": "technology",
            "claim": "A report fact.",
            "evidence": "A report fact.",
            "page_number": 1,
            "block_number": 1,
            "status": "verified",
        }],
        "missing_or_unclear": [],
    })
    response = TestClient(api.app).post("/structured-facts", files={"file": ("report.pdf", make_pdf("A report fact."), "application/pdf")})
    assert response.status_code == 200
    assert response.json()["structured_facts"]["facts"][0]["status"] == "verified"


def test_truncated_structured_response_is_safe(monkeypatch):
    import backend.structured_facts as structured

    candidate = SimpleNamespace(finish_reason="MAX_TOKENS")
    response = SimpleNamespace(candidates=[candidate], text="")
    monkeypatch.setattr(structured, "call_gemini_with_retry", lambda *args, **kwargs: response)
    result = structured.extract_structured_facts([], object())
    assert "smaller report" in result["error"]


def test_structured_input_limit_prevents_gemini_call(monkeypatch):
    import backend.structured_facts as structured
    monkeypatch.setattr(structured, "settings", SimpleNamespace(structured_max_text_chars=5, max_structured_facts=100))
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: (_ for _ in ()).throw(AssertionError("called"))))
    result = structured.extract_structured_facts([{"blocks": [{"page_number": 1, "block_number": 1, "text": "too long"}]}], client)
    assert "smaller report" in result["error"]


def test_paper_generation_stops_at_local_budget(monkeypatch):
    import backend.generate_paper as paper

    facts = {"facts": [
        {"fact_id": "fact_0001", "status": "verified", "claim": "one"},
        {"fact_id": "fact_0002", "status": "verified", "claim": "two"},
    ]}
    plan = [
        {"section_name": "Alpha", "verified_fact_ids": ["fact_0001"], "word_range": (20, 40)},
        {"section_name": "Beta", "verified_fact_ids": ["fact_0002"], "word_range": (20, 40)},
    ]
    monkeypatch.setattr(paper, "plan_sections", lambda facts, client: plan)
    monkeypatch.setattr(paper, "get_remaining_request_budget", lambda: 0)
    result = paper.generate_paper(facts, object())
    assert result.generated_sections == []
    assert [item["section_name"] for item in result.skipped_sections] == ["Alpha", "Beta"]
    assert result.status == "draft_requires_review"


def test_generated_section_is_review_draft_and_keeps_fact_ids(monkeypatch):
    import backend.generate_paper as paper

    facts = {"facts": [{"fact_id": "fact_0001", "status": "verified", "claim": "one"}]}
    monkeypatch.setattr(paper, "plan_sections", lambda facts, client: [{"section_name": "Report-Specific Analysis", "verified_fact_ids": ["fact_0001"], "word_range": (20, 40)}])
    monkeypatch.setattr(paper, "get_remaining_request_budget", lambda: 1)
    monkeypatch.setattr(paper, "generate_section", lambda *args: "Draft prose")
    result = paper.generate_paper(facts, object())
    section = result.generated_sections[0]
    assert section.status == "draft_requires_review"
    assert section.verified_fact_ids == ["fact_0001"]


def test_abstract_cli_writes_file(monkeypatch, tmp_path):
    module = importlib.import_module("backend.generate_abstract")
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"problem_statement": "known"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "get_gemini_client", lambda: object())
    monkeypatch.setattr(module, "generate_abstract", lambda facts, client: "An abstract.")
    monkeypatch.setattr(sys, "argv", ["generate_abstract", str(facts_path)])
    module.main()
    assert (tmp_path / "outputs" / "abstract_facts.txt").read_text(encoding="utf-8").strip() == "An abstract."


def test_backend_modules_import_without_running_cli(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_gemini_client.cache_clear()
    for name in ("backend.extract_facts", "backend.extract_structured_facts", "backend.generate_paper", "backend.generate_abstract"):
        sys.modules.pop(name, None)
        importlib.import_module(name)


def test_gemini_retries_only_transient_errors(monkeypatch):
    import backend.gemini as gemini

    sleeps = []
    monkeypatch.setattr(gemini.time, "sleep", sleeps.append)
    gemini._daily_request_count = 0
    gemini._budget_date = gemini.date.today()

    class Models:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            raise RuntimeError("503 UNAVAILABLE")

    client = SimpleNamespace(models=Models())
    with __import__("pytest").raises(gemini.GeminiServiceError, match="Gemini is busy"):
        gemini.call_gemini_with_retry(client, "model", "prompt")
    assert client.models.calls == 3
    assert len(sleeps) == 2

    sleeps.clear()
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("401 UNAUTHENTICATED"))))
    with __import__("pytest").raises(gemini.GeminiPermanentError):
        gemini.call_gemini_with_retry(client, "model", "prompt")
    assert sleeps == []


def test_gemini_daily_limit_is_enforced(monkeypatch):
    import backend.gemini as gemini

    monkeypatch.setattr(gemini, "settings", SimpleNamespace(gemini_daily_request_limit=1))
    gemini._daily_request_count = 0
    gemini._budget_date = gemini.date.today()
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: "ok"))
    assert gemini.call_gemini_with_retry(client, "model", "prompt") == "ok"
    with __import__("pytest").raises(gemini.GeminiDailyLimitError):
        gemini.call_gemini_with_retry(client, "model", "prompt")


def test_generation_config_uses_low_thinking_and_output_cap():
    from backend.gemini import build_generation_config

    config = build_generation_config()
    assert config.max_output_tokens == 4096
    assert config.thinking_config.thinking_level.value.lower() == "low"


def test_generate_paper_successful_with_verified_facts(monkeypatch):
    from backend import main as api

    monkeypatch.setattr(api, "get_gemini_client", lambda: object())
    monkeypatch.setattr(api, "extract_structured_facts", lambda *args: {
        "project_type": None,
        "facts": [{
            "fact_id": "fact_0001",
            "category": "technology",
            "claim": "A report fact.",
            "evidence": "A report fact.",
            "page_number": 1,
            "block_number": 1,
            "status": "verified",
        }],
        "missing_or_unclear": [],
    })
    monkeypatch.setattr(api, "plan_sections", lambda facts, client: [
        {"section_name": "Methodology", "verified_fact_ids": ["fact_0001"], "word_range": (150, 400)}
    ])
    monkeypatch.setattr(
        api,
        "generate_section",
        lambda section_name, facts, client, min_words, max_words: "This is the generated Methodology text.",
    )
    monkeypatch.setattr(api, "get_remaining_request_budget", lambda: 5)

    response = TestClient(api.app).post(
        "/generate-paper",
        files={"file": ("report.pdf", make_pdf("A report fact."), "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["generated_sections"]) == 1
    assert data["generated_sections"][0]["section_name"] == "Methodology"
    assert data["generated_sections"][0]["content"] == "This is the generated Methodology text."
    assert data["generated_sections"][0]["status"] == "draft_requires_review"
    assert data["generated_sections"][0]["verified_fact_ids"] == ["fact_0001"]
    assert data["remaining_budget"] == 5
    assert "Review the draft sections below" in data["next_action"]


def test_generate_paper_no_verified_facts_returns_questions(monkeypatch):
    from backend import main as api

    monkeypatch.setattr(api, "get_gemini_client", lambda: object())
    monkeypatch.setattr(api, "extract_structured_facts", lambda *args: {
        "project_type": None,
        "facts": [],
        "missing_or_unclear": [{
            "field": "methodology",
            "reason": "No methodology described in report.",
            "question": "What methodology was used in this project?",
        }],
    })
    monkeypatch.setattr(api, "get_remaining_request_budget", lambda: 5)

    response = TestClient(api.app).post(
        "/generate-paper",
        files={"file": ("report.pdf", make_pdf("Unrelated content."), "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["generated_sections"] == []
    assert len(data["missing_or_unclear"]) == 1
    assert data["missing_or_unclear"][0]["question"] == "What methodology was used in this project?"
    assert "What methodology was used in this project?" in data["questions"]
    assert "Provide missing information" in data["next_action"]


def test_generate_paper_returns_503_without_key(monkeypatch):
    from backend import main as api
    from backend.gemini import GeminiConfigurationError

    monkeypatch.setattr(api, "get_gemini_client", lambda: (_ for _ in ()).throw(GeminiConfigurationError("missing")))
    response = TestClient(api.app).post(
        "/generate-paper",
        files={"file": ("report.pdf", make_pdf(), "application/pdf")},
    )
    assert response.status_code == 503


def test_generate_paper_stops_at_budget_limit(monkeypatch):
    from backend import main as api

    monkeypatch.setattr(api, "get_gemini_client", lambda: object())
    monkeypatch.setattr(api, "extract_structured_facts", lambda *args: {
        "project_type": None,
        "facts": [{
            "fact_id": "fact_0001",
            "category": "technology",
            "claim": "A report fact.",
            "evidence": "A report fact.",
            "page_number": 1,
            "block_number": 1,
            "status": "verified",
        }],
        "missing_or_unclear": [],
    })
    monkeypatch.setattr(api, "plan_sections", lambda facts, client: [
        {"section_name": "Section One", "verified_fact_ids": ["fact_0001"], "word_range": (150, 400)},
        {"section_name": "Section Two", "verified_fact_ids": ["fact_0001"], "word_range": (150, 400)},
    ])
    # Budget is 0 before generation starts
    monkeypatch.setattr(api, "get_remaining_request_budget", lambda: 0)

    response = TestClient(api.app).post(
        "/generate-paper",
        files={"file": ("report.pdf", make_pdf("A report fact."), "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["generated_sections"] == []
    assert len(data["skipped_sections"]) == 2
    assert data["skipped_sections"][0]["reason"] == "Local Gemini request budget is exhausted."


