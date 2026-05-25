#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any
from urllib import error, request
import uuid
import zipfile


API_BASE_URL = os.environ.get("PURELINK_API_BASE_URL", "http://localhost:8000").rstrip("/")
API_V1_BASE_URL = f"{API_BASE_URL}/api/v1"
SMOKE_EMAIL = os.environ.get("PURELINK_SMOKE_EMAIL", "purelink-docx-smoke@example.com")
SMOKE_USERNAME = os.environ.get("PURELINK_SMOKE_USERNAME", "purelink-docx-smoke")
SMOKE_PASSWORD = os.environ.get("PURELINK_SMOKE_PASSWORD", "StrongPass123")
DOCX_FILENAME = "purelink_docx_smoke_test.docx"
DOCX_UNIQUE_TOKEN = "DOCX_SMOKE_UNIQUE_TOKEN_2026"
POLL_TIMEOUT_SECONDS = int(os.environ.get("PURELINK_SMOKE_TIMEOUT_SECONDS", "120"))
POLL_INTERVAL_SECONDS = float(os.environ.get("PURELINK_SMOKE_INTERVAL_SECONDS", "2"))


class SmokeTestError(RuntimeError):
    pass


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def fail(message: str, **details: object) -> None:
    print(f"[FAIL] {message}")
    for key, value in details.items():
        print(f"{key}={value}")
    raise SmokeTestError(message)


def build_docx_bytes() -> bytes:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>PureLink Docx Smoke Test</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>PureLink 的 Core RAG 主链路支持 DOCX 文档解析。</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>本文件用于验证 DOCX 上传、处理、索引、检索、回答和引用。</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>答案关键词：{DOCX_UNIQUE_TOKEN}</w:t></w:r>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def http_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    body: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(
        url=f"{API_V1_BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except error.URLError as exc:
        fail("Failed to reach PureLink API", api_base_url=API_V1_BASE_URL, reason=exc)


def http_multipart_upload(
    path: str,
    *,
    token: str,
    field_name: str,
    filename: str,
    content: bytes,
    content_type: str,
    timeout: float = 60.0,
) -> tuple[int, Any]:
    boundary = f"purelink-smoke-{uuid.uuid4().hex}"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(content)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = request.Request(
        url=f"{API_V1_BASE_URL}{path}",
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except error.URLError as exc:
        fail("Failed to upload document to PureLink API", api_base_url=API_V1_BASE_URL, reason=exc)


def ensure_success(status_code: int, body: Any, *, expected: int, message: str) -> None:
    if status_code != expected:
        fail(message, status_code=status_code, response=body)


def extract_detail_text(body: Any) -> str:
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str):
                return message
    if isinstance(body, str):
        return body
    return ""


def register_or_login() -> str:
    register_payload = {
        "email": SMOKE_EMAIL,
        "username": SMOKE_USERNAME,
        "password": SMOKE_PASSWORD,
    }
    status_code, body = http_json("POST", "/auth/register", payload=register_payload)
    if status_code == 201:
        ok("Registered smoke user")
    elif status_code == 409:
        ok("Smoke user already exists, continue with login")
    else:
        fail("Unable to register smoke user", status_code=status_code, response=body)

    login_payload = {
        "identifier": SMOKE_EMAIL,
        "password": SMOKE_PASSWORD,
    }
    status_code, body = http_json("POST", "/auth/login", payload=login_payload)
    ensure_success(status_code, body, expected=200, message="Unable to login smoke user")
    token = body.get("access_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        fail("Login response does not include access_token", response=body)
    ok("Registered or logged in smoke user")
    return token


def create_knowledge_base(token: str) -> int:
    payload = {
        "name": f"PureLink DOCX Smoke KB {int(time.time())}",
        "description": "DOCX smoke test knowledge base.",
    }
    status_code, body = http_json("POST", "/knowledge-bases", token=token, payload=payload)
    ensure_success(status_code, body, expected=201, message="Unable to create knowledge base")
    kb_id = body.get("id") if isinstance(body, dict) else None
    if not isinstance(kb_id, int):
        fail("Knowledge base response does not include id", response=body)
    ok(f"Created knowledge base: {kb_id}")
    return kb_id


def upload_docx(token: str, knowledge_base_id: int, docx_bytes: bytes) -> int:
    status_code, body = http_multipart_upload(
        f"/knowledge-bases/{knowledge_base_id}/documents",
        token=token,
        field_name="file",
        filename=DOCX_FILENAME,
        content=docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    ensure_success(status_code, body, expected=201, message="Unable to upload DOCX document")
    document_id = body.get("id") if isinstance(body, dict) else None
    if not isinstance(document_id, int):
        fail("Upload response does not include document id", response=body)
    ok(f"Uploaded docx document: {document_id}")
    return document_id


def get_document(token: str, knowledge_base_id: int, document_id: int) -> dict[str, Any]:
    status_code, body = http_json("GET", f"/knowledge-bases/{knowledge_base_id}/documents", token=token)
    ensure_success(status_code, body, expected=200, message="Unable to list documents")
    if not isinstance(body, list):
        fail("Document list response is not a list", response=body)
    for item in body:
        if isinstance(item, dict) and item.get("id") == document_id:
            return item
    fail(
        "Uploaded document not found in knowledge base document list",
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )


def get_provider_status() -> dict[str, Any]:
    status_code, body = http_json("GET", "/system/providers")
    ensure_success(status_code, body, expected=200, message="Unable to fetch provider status")
    if not isinstance(body, dict):
        fail("Provider status response is not an object", response=body)
    return body


def get_document_rag_debug(
    token: str,
    knowledge_base_id: int,
    document_id: int,
) -> dict[str, Any]:
    status_code, body = http_json(
        "GET",
        f"/knowledge-bases/{knowledge_base_id}/documents/{document_id}/rag-debug",
        token=token,
    )
    ensure_success(status_code, body, expected=200, message="Unable to fetch document RAG debug")
    if not isinstance(body, dict):
        fail("Document RAG debug response is not an object", response=body)
    return body


def wait_until_indexed(token: str, knowledge_base_id: int, document_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_document: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        document = get_document(token, knowledge_base_id, document_id)
        last_document = document
        status_text = document.get("processing_status")
        print(
            "[INFO] Polling document status",
            f"document_id={document_id}",
            f"processing_status={status_text}",
            f"latest_job_status={document.get('latest_processing_job_status')}",
            f"latest_job_type={document.get('latest_processing_job_type')}",
            f"latest_job_step={document.get('latest_processing_job_step')}",
        )
        if status_text == "indexed":
            debug = get_document_rag_debug(token, knowledge_base_id, document_id)
            if int(debug.get("chunk_count") or 0) < 1:
                fail("Indexed document has no chunks", rag_debug=debug)
            if int(debug.get("citation_unit_count") or 0) < 1:
                fail("Indexed document has no citation units", rag_debug=debug)
            vector_index = debug.get("vector_index") if isinstance(debug.get("vector_index"), dict) else {}
            if vector_index.get("status") != "indexed":
                fail("Indexed document has no indexed vector index", rag_debug=debug)
            ok("Document indexed")
            return document
        if status_text == "failed":
            fail(
                "Document processing failed",
                document_id=document_id,
                error_message=document.get("error_message"),
                latest_processing_job_error_code=document.get("latest_processing_job_error_code"),
                latest_processing_job_step=document.get("latest_processing_job_step"),
            )
        time.sleep(POLL_INTERVAL_SECONDS)

    fail(
        f"Document did not reach indexed within {POLL_TIMEOUT_SECONDS} seconds",
        document_id=document_id,
        last_status=(last_document or {}).get("processing_status"),
        latest_processing_job_status=(last_document or {}).get("latest_processing_job_status"),
        latest_processing_job_step=(last_document or {}).get("latest_processing_job_step"),
    )


def retrieve_docx(token: str, knowledge_base_id: int, document_id: int) -> dict[str, Any]:
    payload = {
        "query": f"PureLink DOCX {DOCX_UNIQUE_TOKEN} 上传 处理 索引 检索 引用",
        "top_k": 3,
    }
    status_code, body = http_json(
        "POST",
        f"/knowledge-bases/{knowledge_base_id}/retrieve",
        token=token,
        payload=payload,
        timeout=60.0,
    )
    ensure_success(status_code, body, expected=200, message="Retrieve request failed")
    if not isinstance(body, dict):
        fail("Retrieve response is not an object", response=body)
    results = body.get("results")
    if not isinstance(results, list) or not results:
        fail("Retrieve returned no DOCX results", response=body)
    if not any(isinstance(item, dict) and item.get("document_id") == document_id for item in results):
        fail("Retrieve did not return uploaded DOCX document", response=body, document_id=document_id)
    ok("Retrieve returned uploaded docx")
    return body


def ask_question(token: str, knowledge_base_id: int) -> dict[str, Any]:
    payload = {
        "question": f"{DOCX_UNIQUE_TOKEN} 说明了什么？",
        "top_k": 3,
    }
    status_code, body = http_json("POST", f"/knowledge-bases/{knowledge_base_id}/ask", token=token, payload=payload, timeout=60.0)
    ensure_success(status_code, body, expected=200, message="Ask request failed")
    if not isinstance(body, dict):
        fail("Ask response is not an object", response=body)
    return body


def validate_answer_and_citations(
    response_body: dict[str, Any],
    *,
    document_id: int,
    allow_external_llm_empty_citations: bool,
) -> None:
    answer = response_body.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        fail("Ask returned empty answer", response=response_body)
    ok("Ask returned non-empty answer")

    citations = response_body.get("citations")
    if not isinstance(citations, list) or not citations:
        if allow_external_llm_empty_citations:
            warn(
                "Ask returned empty citations under an external LLM provider; "
                "retrieve and citation-unit readiness were validated separately."
            )
            return
        fail("Ask returned empty citations", response=response_body)
    ok("Citations returned")

    for citation in citations:
        if not isinstance(citation, dict):
            continue
        if citation.get("document_id") != document_id:
            continue
        source_type = citation.get("source_type")
        document_name = citation.get("document_name")
        locator = citation.get("source_locator")
        locator_text = locator.get("source_locator_text") if isinstance(locator, dict) else None
        if source_type == "docx" or (
            isinstance(document_name, str) and document_name.lower().endswith(".docx")
        ) or (
            isinstance(locator_text, str) and ("section:" in locator_text or "chars:" in locator_text)
        ):
            ok("Citation points to uploaded docx")
            return

    fail("No citation points to uploaded docx", response=response_body, document_id=document_id)


def ensure_api_health() -> None:
    status_code, body = http_json("GET", "/health")
    ensure_success(status_code, body, expected=200, message="PureLink API health check failed")


def main() -> int:
    try:
        ensure_api_health()
        with tempfile.TemporaryDirectory(prefix="purelink-docx-smoke-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            docx_path = tmp_path / DOCX_FILENAME
            docx_bytes = build_docx_bytes()
            docx_path.write_bytes(docx_bytes)

            token = register_or_login()
            knowledge_base_id = create_knowledge_base(token)
            document_id = upload_docx(token, knowledge_base_id, docx_bytes)
            wait_until_indexed(token, knowledge_base_id, document_id)
            retrieve_docx(token, knowledge_base_id, document_id)
            provider_status = get_provider_status()
            llm_status = provider_status.get("llm") if isinstance(provider_status, dict) else {}
            llm_provider = llm_status.get("provider") if isinstance(llm_status, dict) else None
            ask_response = ask_question(token, knowledge_base_id)
            validate_answer_and_citations(
                ask_response,
                document_id=document_id,
                allow_external_llm_empty_citations=llm_provider != "heuristic",
            )
            print("PureLink docx RAG smoke test passed.")
            return 0
    except SmokeTestError:
        return 1
    except Exception as exc:  # pragma: no cover - defensive smoke guard
        print(f"[FAIL] Unexpected smoke test failure: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
