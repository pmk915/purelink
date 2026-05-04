from __future__ import annotations

import asyncio
import io
import json
from datetime import timedelta
from pathlib import Path
import wave
import zipfile
from xml.sax.saxutils import escape as xml_escape

import pytest
import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from PIL import Image, ImageDraw
except ModuleNotFoundError:  # pragma: no cover - optional extension test dependency
    Image = None
    ImageDraw = None

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.document_task import DocumentTask
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentTaskStatus,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
)
from app.models.processing_job import ProcessingJob
from app.services.document_embedding import DocumentEmbeddingError
from app.services.document_processing import (
    DocumentProcessingError,
    ExtractedTextSegment,
    RenderedPDFPage,
    extract_text_from_txt,
)
from app.services.asr_provider import ASRProviderError, ASRResult, ASRSegment
from app.services.ocr_provider import OCRProviderError, OCRRegion, OCRResult
from app.services import document_indexing as document_indexing_service
from app.services import processing_worker as processing_worker_service
from app.services.processing_job import (
    acquire_processing_job,
    fail_timed_out_processing_jobs,
)


load_all_models()


class CapturedProcessingJobRunner:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []

    def submit_processing_job(
        self,
        *,
        job: ProcessingJob,
    ) -> str:
        self.submissions.append(
            {
                "job_id": job.id,
                "document_id": job.document_id,
                "job_type": job.job_type.value,
            }
        )
        return str(job.id)

    def run_next(self) -> None:
        submission = self.submissions.pop(0)
        processing_worker_service.execute_processing_job(
            job_id=submission["job_id"],
            worker_name=processing_worker_service.REDIS_PROCESSING_WORKER_NAME,
        )

    def run_all(self) -> None:
        queued_count = len(self.submissions)
        for _ in range(queued_count):
            self.run_next()

    def drain_all(self) -> None:
        while self.submissions:
            self.run_next()


def _assert_api_source_locator(
    locator: dict[str, object] | None,
    *,
    kind: str,
    source_locator_text: str,
    page_number: int | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    section_title: str | None = None,
) -> None:
    assert isinstance(locator, dict)
    assert locator["kind"] == kind
    assert locator["source_locator_text"] == source_locator_text
    if page_number is not None:
        assert locator["page_number"] == page_number
    if start_time is not None:
        assert locator["start_time"] == start_time
    if end_time is not None:
        assert locator["end_time"] == end_time
    if section_title is not None:
        assert locator["section_title"] == section_title


@pytest.fixture
def test_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    try:
        yield testing_session_local
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
async def document_client(
    test_session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncClient:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PARSED_DIR", str(tmp_path / "parsed"))
    monkeypatch.setenv("CHUNK_DIR", str(tmp_path / "chunks"))
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path / "vector_store"))
    get_settings.cache_clear()

    def default_submit_processing_job(*, job: ProcessingJob) -> str:
        return str(job.id)

    monkeypatch.setattr(
        processing_worker_service,
        "submit_processing_job",
        default_submit_processing_job,
    )
    monkeypatch.setattr(
        processing_worker_service,
        "open_processing_session",
        lambda: test_session_factory(),
    )

    async def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def processing_job_runner(
    test_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> CapturedProcessingJobRunner:
    runner = CapturedProcessingJobRunner()
    monkeypatch.setattr(
        processing_worker_service,
        "submit_processing_job",
        runner.submit_processing_job,
    )
    monkeypatch.setattr(
        processing_worker_service,
        "open_processing_session",
        lambda: test_session_factory(),
    )
    return runner


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str,
    username: str,
    password: str = "StrongPass123",
) -> dict[str, str | int]:
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200

    return {
        "access_token": login_response.json()["access_token"],
        "user_id": register_response.json()["id"],
    }


async def _create_personal_knowledge_base(
    client: AsyncClient,
    *,
    access_token: str,
    name: str,
) -> int:
    response = await client.post(
        "/api/v1/knowledge-bases",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_team(client: AsyncClient, *, access_token: str, name: str) -> int:
    response = await client.post(
        "/api/v1/teams",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_team_invite(
    client: AsyncClient,
    *,
    access_token: str,
    team_id: int,
) -> str:
    response = await client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expires_in_days": 7},
    )
    assert response.status_code == 201
    return response.json()["code"]


async def _join_team(
    client: AsyncClient,
    *,
    access_token: str,
    code: str,
) -> None:
    response = await client.post(
        "/api/v1/team-invites/join",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": code},
    )
    assert response.status_code == 200


async def _create_team_knowledge_base(
    client: AsyncClient,
    *,
    access_token: str,
    team_id: int,
    name: str,
) -> int:
    response = await client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _submit_manual_index_job(
    client: AsyncClient,
    *,
    path: str,
    headers: dict[str, str],
    processing_job_runner: CapturedProcessingJobRunner,
) -> dict[str, object]:
    response = await client.post(path, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["job_type"] == "document_index"
    assert body["job_status"] == "queued"
    assert body["trigger_type"] == "index"
    processing_job_runner.run_all()
    processing_job_runner.run_all()
    return body


def _build_minimal_pdf(*, text: str) -> bytes:
    escaped_text = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )
    stream = f"BT\n/F1 12 Tf\n72 720 Td\n({escaped_text}) Tj\nET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n",
        (
            f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]
    return b"%PDF-1.4\n" + b"".join(objects) + b"%%EOF\n"


def _build_minimal_docx(*, paragraphs: list[tuple[str, str | None]]) -> bytes:
    paragraph_xml = []
    for text, style_id in paragraphs:
        style_xml = (
            f'<w:pPr><w:pStyle w:val="{xml_escape(style_id)}"/></w:pPr>'
            if style_id
            else ""
        )
        paragraph_xml.append(
            "<w:p>"
            f"{style_xml}"
            f"<w:r><w:t>{xml_escape(text)}</w:t></w:r>"
            "</w:p>"
        )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(paragraph_xml)}</w:body>"
        "</w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _build_test_image_bytes(
    *,
    text: str,
    image_format: str = "PNG",
) -> bytes:
    image = Image.new("RGB", (960, 240), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def _build_test_wav_bytes(
    *,
    duration_seconds: float = 1.0,
    sample_rate: int = 16_000,
) -> bytes:
    frame_count = max(1, int(duration_seconds * sample_rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def _build_test_video_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


def _build_scanned_pdf_bytes(*, page_texts: list[str]) -> bytes:
    images: list[Image.Image] = []
    try:
        for page_text in page_texts:
            image = Image.new("RGB", (1240, 1754), color="white")
            draw = ImageDraw.Draw(image)
            draw.text((80, 120), page_text, fill="black")
            images.append(image)

        if not images:
            raise AssertionError("At least one page is required for a scanned PDF fixture.")

        buffer = io.BytesIO()
        first_image, *remaining_images = images
        first_image.save(
            buffer,
            format="PDF",
            save_all=True,
            append_images=remaining_images,
        )
        return buffer.getvalue()
    finally:
        for image in images:
            image.close()


class FakeOCRProvider:
    def __init__(
        self,
        *,
        result: OCRResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    def extract_text(self, image_path: Path) -> OCRResult:
        assert image_path.exists()
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("FakeOCRProvider requires a result or an error.")
        return self.result


class SequentialOCRProvider:
    def __init__(self, *, results: list[OCRResult]) -> None:
        if not results:
            raise AssertionError("SequentialOCRProvider requires at least one OCR result.")
        self.results = results
        self.index = 0
        self.provider_name = results[0].provider_name
        self.provider_version = results[0].provider_version

    def extract_text(self, image_path: Path) -> OCRResult:
        assert image_path.exists()
        if self.index >= len(self.results):
            raise AssertionError("SequentialOCRProvider ran out of OCR results.")
        result = self.results[self.index]
        self.index += 1
        return result


class FakeASRProvider:
    def __init__(
        self,
        *,
        result: ASRResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    def transcribe(self, audio_path: Path) -> ASRResult:
        assert audio_path.exists()
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("FakeASRProvider requires a result or an error.")
        return self.result


def _write_extracted_video_audio(
    *,
    output_path: Path,
    duration_seconds: float = 1.0,
) -> Path:
    output_path.write_bytes(_build_test_wav_bytes(duration_seconds=duration_seconds))
    return output_path


def _fake_rendered_pdf_pages(
    *,
    output_dir: Path,
    page_texts: list[str],
) -> list[RenderedPDFPage]:
    rendered_pages: list[RenderedPDFPage] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        image_path = output_dir / f"page-{page_number}.png"
        image_path.write_bytes(_build_test_image_bytes(text=page_text, image_format="PNG"))
        rendered_pages.append(
            RenderedPDFPage(
                page_number=page_number,
                image_path=image_path,
            )
        )
    return rendered_pages


@pytest.mark.anyio
async def test_personal_document_upload_and_list_respect_owner_boundary(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="personal-docs-owner@example.com",
        username="personal-docs-owner",
    )
    bob = await _register_and_login(
        document_client,
        email="personal-docs-other@example.com",
        username="personal-docs-other",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Alice Private Docs",
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("alice-notes.txt", b"Alice private document", "text/plain")},
    )

    assert upload_response.status_code == 201
    document_body = upload_response.json()
    assert document_body["knowledge_base_id"] == knowledge_base_id
    assert document_body["owner_id"] == alice["user_id"]
    assert document_body["submitted_by"] == alice["user_id"]
    assert document_body["original_filename"] == "alice-notes.txt"
    assert document_body["file_type"] == "text/plain"
    assert document_body["review_status"] == "not_required"
    assert document_body["processing_status"] == "processing"
    assert document_body["sha256"] == "0fabec4cbb28eac6a79a222c30b525bd940c1f07d06d34d9f82fdaa8a6670349"
    assert document_body["latest_processing_job_status"] == "queued"
    assert document_body["latest_processing_job_type"] == "document_process"
    assert document_body["reviewed_by"] is None
    assert document_body["reviewed_at"] is None
    assert "personal/knowledge_base_" in document_body["storage_path"]

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"Alice private document"

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["id"] == document_body["id"]

    other_list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=bob_headers,
    )
    other_upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=bob_headers,
        files={"file": ("intrusion.txt", b"nope", "text/plain")},
    )
    assert other_list_response.status_code == 404
    assert other_upload_response.status_code == 404


@pytest.mark.anyio
async def test_personal_upload_rejects_file_larger_than_configured_limit(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "0")
    get_settings.cache_clear()

    alice = await _register_and_login(
        document_client,
        email="upload-too-large@example.com",
        username="upload-too-large",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Too Large KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("too-large.txt", b"x", "text/plain")},
    )

    assert upload_response.status_code == 413
    assert upload_response.json()["detail"]["error_code"] == "FILE_TOO_LARGE"


@pytest.mark.anyio
async def test_personal_upload_rejects_image_when_core_ocr_is_disabled(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="upload-image-unsupported@example.com",
        username="upload-image-unsupported",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Image Unsupported KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("whiteboard.png", b"fake png payload", "image/png")},
    )

    assert upload_response.status_code == 400
    assert upload_response.json()["detail"]["error_code"] == "FEATURE_NOT_ENABLED"


@pytest.mark.anyio
async def test_personal_upload_rejects_video_when_core_media_is_disabled(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="upload-video-unsupported@example.com",
        username="upload-video-unsupported",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Video Unsupported KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("standup.mp4", b"fake mp4 payload", "video/mp4")},
    )

    assert upload_response.status_code == 400
    assert upload_response.json()["detail"]["error_code"] == "FEATURE_NOT_ENABLED"


@pytest.mark.anyio
async def test_personal_upload_duplicate_in_same_knowledge_base_reuses_existing_document(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="upload-duplicate@example.com",
        username="upload-duplicate",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Duplicate Upload KB",
    )

    first_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("first.txt", b"duplicate upload content", "text/plain")},
    )
    second_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("second.txt", b"duplicate upload content", "text/plain")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"]["error_code"] == "DUPLICATE_DOCUMENT"

    with test_session_factory() as db:
        documents = list(
            db.scalars(
                select(Document).where(Document.knowledge_base_id == knowledge_base_id)
            )
        )
        jobs = list(
            db.scalars(
                select(ProcessingJob).where(ProcessingJob.document_id == documents[0].id)
            )
        )

    assert len(documents) == 1
    assert len(jobs) == 1
    assert jobs[0].job_type == ProcessingJobType.DOCUMENT_PROCESS


@pytest.mark.anyio
async def test_personal_upload_allows_same_sha256_in_different_knowledge_bases(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="upload-same-sha-different-kb@example.com",
        username="upload-same-sha-different-kb",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    first_kb_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Same SHA First KB",
    )
    second_kb_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Same SHA Second KB",
    )

    first_response = await document_client.post(
        f"/api/v1/knowledge-bases/{first_kb_id}/documents",
        headers=alice_headers,
        files={"file": ("shared-a.txt", b"shared sha content", "text/plain")},
    )
    second_response = await document_client.post(
        f"/api/v1/knowledge-bases/{second_kb_id}/documents",
        headers=alice_headers,
        files={"file": ("shared-b.txt", b"shared sha content", "text/plain")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["sha256"] == second_response.json()["sha256"]

    with test_session_factory() as db:
        documents = list(
            db.scalars(
                select(Document)
                .where(Document.sha256 == first_response.json()["sha256"])
                .order_by(Document.id.asc())
            )
        )

    assert len(documents) == 2
    assert {item.knowledge_base_id for item in documents} == {first_kb_id, second_kb_id}


@pytest.mark.anyio
async def test_personal_upload_rejects_when_user_active_job_limit_is_reached(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
) -> None:
    monkeypatch.setenv("MAX_ACTIVE_JOBS_PER_USER", "1")
    get_settings.cache_clear()

    alice = await _register_and_login(
        document_client,
        email="upload-active-limit@example.com",
        username="upload-active-limit",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Active Limit KB",
    )

    first_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("active-one.txt", b"active one", "text/plain")},
    )
    second_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("active-two.txt", b"active two", "text/plain")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert second_response.json()["detail"]["error_code"] == "TOO_MANY_ACTIVE_JOBS"

    with test_session_factory() as db:
        documents = list(
            db.scalars(
                select(Document).where(Document.knowledge_base_id == knowledge_base_id)
            )
        )

    assert len(documents) == 1


@pytest.mark.anyio
async def test_personal_concurrent_duplicate_upload_creates_one_document_process_job(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="upload-concurrent-duplicate@example.com",
        username="upload-concurrent-duplicate",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Concurrent Duplicate KB",
    )

    async def upload_copy(filename: str):
        return await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
            headers=alice_headers,
            files={"file": (filename, b"same concurrent content", "text/plain")},
        )

    responses = await asyncio.gather(
        upload_copy("concurrent-a.txt"),
        upload_copy("concurrent-b.txt"),
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409]

    with test_session_factory() as db:
        documents = list(
            db.scalars(
                select(Document).where(Document.knowledge_base_id == knowledge_base_id)
            )
        )
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .join(Document, Document.id == ProcessingJob.document_id)
                .where(Document.knowledge_base_id == knowledge_base_id)
            )
        )

    assert len(documents) == 1
    assert len(jobs) == 1
    assert jobs[0].job_type == ProcessingJobType.DOCUMENT_PROCESS


@pytest.mark.anyio
async def test_team_document_submission_is_pending_review_and_not_visible_as_approved(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="team-docs-admin@example.com",
        username="team-docs-admin",
    )
    member = await _register_and_login(
        document_client,
        email="team-docs-member@example.com",
        username="team-docs-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="team-docs-outsider@example.com",
        username="team-docs-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Review Flow Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Shared Review Docs",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("team-proposal.pdf", b"team review content", "application/pdf")},
    )

    assert upload_response.status_code == 201
    document_body = upload_response.json()
    assert document_body["knowledge_base_id"] == knowledge_base_id
    assert document_body["owner_id"] == member["user_id"]
    assert document_body["submitted_by"] == member["user_id"]
    assert document_body["review_status"] == "pending_review"
    assert document_body["processing_status"] == "uploaded"
    assert document_body["reviewed_by"] is None
    assert document_body["reviewed_at"] is None
    assert document_body["review_comment"] is None
    assert document_body["review_status"] != "approved"
    assert f"team/team_{team_id}/knowledge_base_{knowledge_base_id}/" in document_body["storage_path"]

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"team review content"

    member_list_response = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
    )
    admin_list_response = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=admin_headers,
    )
    outsider_list_response = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=outsider_headers,
    )
    outsider_upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=outsider_headers,
        files={"file": ("outsider.txt", b"forbidden", "text/plain")},
    )

    assert member_list_response.status_code == 200
    assert admin_list_response.status_code == 200
    assert outsider_list_response.status_code == 404
    assert outsider_upload_response.status_code == 404

    member_documents = member_list_response.json()
    admin_documents = admin_list_response.json()
    assert len(member_documents) == 1
    assert len(admin_documents) == 1
    assert member_documents[0]["id"] == document_body["id"]
    assert admin_documents[0]["review_status"] == "pending_review"
    assert admin_documents[0]["processing_status"] == "uploaded"


@pytest.mark.anyio
async def test_team_admin_upload_is_approved_without_review_queue(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="team-admin-upload@example.com",
        username="team-admin-upload",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Admin Upload Team",
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Admin Upload KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=admin_headers,
        files={"file": ("admin-runbook.txt", b"admin approved content", "text/plain")},
    )

    assert upload_response.status_code == 201
    document_body = upload_response.json()
    assert document_body["review_status"] == "approved"
    assert document_body["reviewed_by"] == admin["user_id"]
    assert document_body["reviewed_at"] is not None
    assert document_body["processing_status"] == "processing"
    assert document_body["latest_processing_job_status"] == "queued"

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"admin approved content"

    review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks.status_code == 200
    assert review_tasks.json() == []


@pytest.mark.anyio
async def test_team_document_review_permissions_and_state_transitions(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="review-admin@example.com",
        username="review-admin",
    )
    member = await _register_and_login(
        document_client,
        email="review-member@example.com",
        username="review-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="review-outsider@example.com",
        username="review-outsider",
    )
    other_admin = await _register_and_login(
        document_client,
        email="other-review-admin@example.com",
        username="other-review-admin",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}
    other_admin_headers = {"Authorization": f"Bearer {other_admin['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Review Admin Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Review Queue Docs",
    )
    other_team_id = await _create_team(
        document_client,
        access_token=str(other_admin["access_token"]),
        name="Other Review Team",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("pending-review.txt", b"pending review", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    member_review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=member_headers,
    )
    outsider_review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=outsider_headers,
    )
    member_approve = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=member_headers,
    )
    outsider_approve = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=outsider_headers,
    )
    wrong_team_approve = await document_client.post(
        f"/api/v1/teams/{other_team_id}/documents/{document_id}/approve",
        headers=other_admin_headers,
    )

    assert member_review_tasks.status_code == 403
    assert outsider_review_tasks.status_code == 404
    assert member_approve.status_code == 403
    assert outsider_approve.status_code == 404
    assert wrong_team_approve.status_code == 404

    review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks.status_code == 200
    tasks_body = review_tasks.json()
    assert len(tasks_body) == 1
    assert tasks_body[0]["id"] == document_id
    assert tasks_body[0]["review_status"] == "pending_review"
    assert tasks_body[0]["processing_status"] == "uploaded"

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    approved_body = approve_response.json()
    assert approved_body["review_status"] == "approved"
    assert approved_body["processing_status"] == "uploaded"
    assert approved_body["reviewed_by"] == admin["user_id"]
    assert approved_body["reviewed_at"] is not None
    assert approved_body["review_comment"] is None

    review_tasks_after_approve = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks_after_approve.status_code == 200
    assert review_tasks_after_approve.json() == []

    repeated_approve = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    repeated_reject = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/reject",
        headers=admin_headers,
        json={"review_comment": "Too late"},
    )
    assert repeated_approve.status_code == 409
    assert repeated_reject.status_code == 409


@pytest.mark.anyio
async def test_team_document_reject_records_reason_and_blocks_repeat_review(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="reject-admin@example.com",
        username="reject-admin",
    )
    member = await _register_and_login(
        document_client,
        email="reject-member@example.com",
        username="reject-member",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Reject Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Reject Queue Docs",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("reject-me.txt", b"reject me", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    reject_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/reject",
        headers=admin_headers,
        json={"review_comment": "File content does not meet team policy."},
    )
    assert reject_response.status_code == 200
    rejected_body = reject_response.json()
    assert rejected_body["review_status"] == "rejected"
    assert rejected_body["processing_status"] == "uploaded"
    assert rejected_body["reviewed_by"] == admin["user_id"]
    assert rejected_body["reviewed_at"] is not None
    assert rejected_body["review_comment"] == "File content does not meet team policy."

    review_tasks_after_reject = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks_after_reject.status_code == 200
    assert review_tasks_after_reject.json() == []

    repeated_reject = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/reject",
        headers=admin_headers,
        json={"review_comment": "Still rejected"},
    )
    assert repeated_reject.status_code == 409


@pytest.mark.anyio
async def test_personal_txt_document_can_be_parsed_and_saved_to_local_result(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="parse-personal@example.com",
        username="parse-personal",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Parse Personal KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("notes.txt", b"line one\nline two", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200
    parse_body = parse_response.json()
    assert parse_body["document_id"] == document_id
    assert parse_body["knowledge_base_id"] == knowledge_base_id
    assert parse_body["processing_status"] == "parsed"
    assert parse_body["parser"] == "plain_text"
    assert parse_body["extracted_char_count"] == len("line one\nline two")

    parsed_file = tmp_path / "parsed" / parse_body["parsed_path"]
    assert parsed_file.exists()
    parsed_payload = json.loads(parsed_file.read_text(encoding="utf-8"))
    assert parsed_payload["document_id"] == document_id
    assert parsed_payload["content"] == "line one\nline two"
    assert parsed_payload["parser"] == "plain_text"

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "parsed"


@pytest.mark.anyio
async def test_team_document_must_be_approved_before_it_can_be_parsed(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="parse-team-admin@example.com",
        username="parse-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="parse-team-member@example.com",
        username="parse-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="parse-team-outsider@example.com",
        username="parse-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Parse Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Parse Team KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("team-notes.md", b"# Heading\n\nApproved content", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    outsider_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=outsider_headers,
    )
    assert parse_before_approval.status_code == 409
    assert outsider_parse.status_code == 404

    list_before_approval = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=admin_headers,
    )
    assert list_before_approval.status_code == 200
    assert list_before_approval.json()[0]["processing_status"] == "uploaded"

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["review_status"] == "approved"

    parse_after_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    assert parse_after_approval.status_code == 200
    parse_body = parse_after_approval.json()
    assert parse_body["processing_status"] == "parsed"
    assert parse_body["parser"] == "markdown"

    parsed_file = tmp_path / "parsed" / parse_body["parsed_path"]
    assert parsed_file.exists()
    parsed_payload = json.loads(parsed_file.read_text(encoding="utf-8"))
    assert parsed_payload["scope"] == "team"
    assert parsed_payload["team_id"] == team_id
    assert parsed_payload["content"] == "# Heading\n\nApproved content"


@pytest.mark.anyio
async def test_unsupported_document_parse_marks_processing_failed(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="parse-fail@example.com",
        username="parse-fail",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Parse Fail KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("unsupported.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 400

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "failed"


@pytest.mark.anyio
async def test_invalid_chunk_input_marks_processing_failed(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="chunk-fail@example.com",
        username="chunk-fail",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Chunk Fail KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("chunk-fail.txt", b"valid content", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    parsed_file = tmp_path / "parsed" / parse_response.json()["parsed_path"]
    parsed_file.write_text(
        json.dumps({"content": ""}),
        encoding="utf-8",
    )

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 400

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "failed"


@pytest.mark.anyio
async def test_personal_document_parse_task_creation_and_status_query(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="task-personal-owner@example.com",
        username="task-personal-owner",
    )
    bob = await _register_and_login(
        document_client,
        email="task-personal-other@example.com",
        username="task-personal-other",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Task KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("task-notes.txt", b"task me", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    create_task_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert create_task_response.status_code == 201
    task_body = create_task_response.json()
    task_id = task_body["id"]
    assert task_body["document_id"] == document_id
    assert task_body["task_type"] == "parse"
    assert task_body["status"] == "pending"
    assert task_body["error_message"] is None
    assert task_body["retry_count"] == 0
    assert task_body["started_at"] is None
    assert task_body["finished_at"] is None

    get_owner_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=alice_headers,
    )
    get_other_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=bob_headers,
    )
    assert get_owner_task.status_code == 200
    assert get_owner_task.json()["id"] == task_id
    assert get_other_task.status_code == 404


@pytest.mark.anyio
async def test_personal_document_parse_task_rejects_duplicate_active_tasks(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="task-dedupe-owner@example.com",
        username="task-dedupe-owner",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Dedupe KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("task-dedupe.txt", b"dedupe me", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    first_task_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert first_task_response.status_code == 201
    first_task_id = first_task_response.json()["id"]

    duplicate_pending_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert duplicate_pending_response.status_code == 409

    with test_session_factory() as db:
        task = db.get(DocumentTask, first_task_id)
        assert task is not None
        task.status = DocumentTaskStatus.SUCCEEDED
        db.commit()

    create_after_completion = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert create_after_completion.status_code == 201


@pytest.mark.anyio
async def test_personal_document_chunk_embed_and_index_task_creation_requires_prerequisites(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="task-chain-personal@example.com",
        username="task-chain-personal",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Task Chain KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("task-chain.txt", b"task chain content", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    chunk_before_parse = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=alice_headers,
    )
    embed_before_parse = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=alice_headers,
    )
    index_before_parse = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=alice_headers,
    )
    assert chunk_before_parse.status_code == 409
    assert embed_before_parse.status_code == 409
    assert index_before_parse.status_code == 409

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    chunk_task = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=alice_headers,
    )
    embed_before_chunk = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=alice_headers,
    )
    index_before_chunk = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=alice_headers,
    )
    assert chunk_task.status_code == 201
    assert chunk_task.json()["task_type"] == "chunk"
    assert chunk_task.json()["status"] == "pending"
    assert embed_before_chunk.status_code == 409
    assert index_before_chunk.status_code == 409

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 200

    embed_task = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=alice_headers,
    )
    index_task = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=alice_headers,
    )
    assert embed_task.status_code == 201
    assert embed_task.json()["task_type"] == "embed"
    assert index_task.status_code == 201
    assert index_task.json()["task_type"] == "index"


@pytest.mark.anyio
async def test_team_document_parse_task_creation_requires_approved_document_and_member_access(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="task-team-admin@example.com",
        username="task-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="task-team-member@example.com",
        username="task-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="task-team-outsider@example.com",
        username="task-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Task Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Task Team KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("task-team.md", b"# Task Team", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    create_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    outsider_create = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=outsider_headers,
    )
    assert create_before_approval.status_code == 409
    assert outsider_create.status_code == 404

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    create_after_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    assert create_after_approval.status_code == 201
    task_body = create_after_approval.json()
    task_id = task_body["id"]
    assert task_body["document_id"] == document_id
    assert task_body["task_type"] == "parse"
    assert task_body["status"] == "pending"

    admin_get_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=admin_headers,
    )
    member_get_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=member_headers,
    )
    outsider_get_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=outsider_headers,
    )
    assert admin_get_task.status_code == 200
    assert member_get_task.status_code == 200
    assert outsider_get_task.status_code == 404


@pytest.mark.anyio
async def test_team_document_parse_task_rejects_duplicate_processing_task(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="task-processing-admin@example.com",
        username="task-processing-admin",
    )
    member = await _register_and_login(
        document_client,
        email="task-processing-member@example.com",
        username="task-processing-member",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Task Processing Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Task Processing KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("task-processing.md", b"# approved", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    first_task_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    assert first_task_response.status_code == 201
    first_task_id = first_task_response.json()["id"]

    with test_session_factory() as db:
        task = db.get(DocumentTask, first_task_id)
        assert task is not None
        task.status = DocumentTaskStatus.PROCESSING
        db.commit()

    duplicate_processing_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    assert duplicate_processing_response.status_code == 409


@pytest.mark.anyio
async def test_team_document_chunk_embed_and_index_tasks_require_member_access_and_approval(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="task-chain-team-admin@example.com",
        username="task-chain-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="task-chain-team-member@example.com",
        username="task-chain-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="task-chain-team-outsider@example.com",
        username="task-chain-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Task Chain Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Task Chain Team KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("task-chain-team.md", b"team task chain", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    outsider_chunk_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=outsider_headers,
    )
    member_chunk_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=member_headers,
    )
    assert outsider_chunk_task.status_code == 404
    assert member_chunk_before_approval.status_code == 409

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    chunk_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=member_headers,
    )
    embed_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=member_headers,
    )
    index_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=member_headers,
    )
    assert chunk_before_parse.status_code == 409
    assert embed_before_parse.status_code == 409
    assert index_before_parse.status_code == 409

    parse_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    assert parse_response.status_code == 200

    chunk_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=member_headers,
    )
    assert chunk_task.status_code == 201
    assert chunk_task.json()["task_type"] == "chunk"

    chunk_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_response.status_code == 200

    embed_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=member_headers,
    )
    index_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=member_headers,
    )
    assert embed_task.status_code == 201
    assert embed_task.json()["task_type"] == "embed"
    assert index_task.status_code == 201
    assert index_task.json()["task_type"] == "index"


@pytest.mark.anyio
async def test_personal_parsed_document_can_be_chunked_to_local_result(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="chunk-personal@example.com",
        username="chunk-personal",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Chunk Personal KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("chunk-notes.txt", b"alpha\n\nbeta\n\ngamma", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 200
    chunk_body = chunk_response.json()
    assert chunk_body["document_id"] == document_id
    assert chunk_body["processing_status"] == "parsed"
    assert chunk_body["chunk_count"] >= 1
    assert chunk_body["source_parsed_path"].endswith(f"document_{document_id}.json")

    chunk_file = tmp_path / "chunks" / chunk_body["chunked_path"]
    assert chunk_file.exists()
    chunk_payload = json.loads(chunk_file.read_text(encoding="utf-8"))
    assert chunk_payload["document_id"] == document_id
    assert chunk_payload["chunk_count"] == chunk_body["chunk_count"]
    assert chunk_payload["chunks"][0]["chunk_id"] == f"{document_id}:0"
    assert "alpha" in chunk_payload["chunks"][0]["text"]


@pytest.mark.anyio
async def test_team_document_must_be_approved_and_parsed_before_chunking(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="chunk-team-admin@example.com",
        username="chunk-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="chunk-team-member@example.com",
        username="chunk-team-member",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Chunk Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Chunk Team KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("chunk-team.md", b"# Heading\n\nApproved chunk content", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    chunk_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_before_approval.status_code == 409

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    chunk_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_before_parse.status_code == 409

    parse_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    assert parse_response.status_code == 200

    chunk_after_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_after_parse.status_code == 200
    chunk_body = chunk_after_parse.json()
    assert chunk_body["processing_status"] == "parsed"
    assert chunk_body["chunk_count"] >= 1

    chunk_file = tmp_path / "chunks" / chunk_body["chunked_path"]
    assert chunk_file.exists()
    chunk_payload = json.loads(chunk_file.read_text(encoding="utf-8"))
    assert chunk_payload["team_id"] == team_id
    assert chunk_payload["source_parsed_path"].endswith(f"document_{document_id}.json")


@pytest.mark.anyio
async def test_personal_document_can_be_embedded_and_retrieved(
    document_client: AsyncClient,
    tmp_path: Path,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="embed-personal@example.com",
        username="embed-personal",
    )
    bob = await _register_and_login(
        document_client,
        email="embed-personal-other@example.com",
        username="embed-personal-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Retrieval KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("embed-notes.txt", b"alpha retrieval target\n\nbeta gamma", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 200

    embed_body = await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
        processing_job_runner=processing_job_runner,
    )
    assert embed_body["document_id"] == document_id

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    assert index_file.exists()
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert index_payload["knowledge_base_id"] == knowledge_base_id
    assert index_payload["index_scheme"] == "json_vector_index_v1"
    assert index_payload["embedding_scheme"] == "hashed_bow_v1"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "retrieval target", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["query"] == "retrieval target"
    assert retrieve_body["top_k"] == 3
    assert retrieve_body["results"]
    first_result = retrieve_body["results"][0]
    assert first_result["document_id"] == document_id
    assert first_result["knowledge_base_id"] == knowledge_base_id
    assert first_result["scope"] == "personal"
    assert first_result["team_id"] is None
    assert first_result["document_name"] == "embed-notes.txt"
    assert first_result["source_type"] == "text"
    assert first_result["page_number"] is None
    assert first_result["section_title"] is None
    assert first_result["snippet"]
    assert "retrieval target" in first_result["text"]

    other_user_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=bob_headers,
        json={"query": "retrieval target"},
    )
    assert other_user_response.status_code == 404


@pytest.mark.anyio
async def test_team_unapproved_document_cannot_be_embedded_or_retrieved(
    document_client: AsyncClient,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="embed-team-admin@example.com",
        username="embed-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="embed-team-member@example.com",
        username="embed-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="embed-team-outsider@example.com",
        username="embed-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Embedding Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Embedding Team KB",
    )

    pending_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("pending-note.md", b"pendingonlytoken draft review", "text/markdown")},
    )
    assert pending_upload.status_code == 201
    pending_document_id = pending_upload.json()["id"]

    pending_embed = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{pending_document_id}/embed",
        headers=member_headers,
    )
    assert pending_embed.status_code == 409

    approved_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("approved-note.md", b"approvedtoken searchable knowledge", "text/markdown")},
    )
    assert approved_upload.status_code == 201
    approved_document_id = approved_upload.json()["id"]

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{approved_document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    parse_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/parse",
        headers=member_headers,
    )
    assert parse_response.status_code == 200

    chunk_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_response.status_code == 200

    embed_body = await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/embed",
        headers=member_headers,
        processing_job_runner=processing_job_runner,
    )
    assert embed_body["document_id"] == approved_document_id

    retrieve_pending_token = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=member_headers,
        json={"query": "pendingonlytoken", "top_k": 5},
    )
    assert retrieve_pending_token.status_code == 200
    assert retrieve_pending_token.json()["results"] == []

    retrieve_approved = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=member_headers,
        json={"query": "approvedtoken", "top_k": 5},
    )
    assert retrieve_approved.status_code == 200
    approved_results = retrieve_approved.json()["results"]
    assert approved_results
    assert approved_results[0]["document_id"] == approved_document_id
    assert approved_results[0]["scope"] == "team"
    assert approved_results[0]["team_id"] == team_id

    outsider_retrieve = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=outsider_headers,
        json={"query": "approvedtoken"},
    )
    assert outsider_retrieve.status_code == 404


@pytest.mark.anyio
async def test_personal_knowledge_base_ask_returns_answer_and_citations(
    document_client: AsyncClient,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="ask-personal@example.com",
        username="ask-personal",
    )
    bob = await _register_and_login(
        document_client,
        email="ask-personal-other@example.com",
        username="ask-personal-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal QA KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("qa-notes.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
            headers=alice_headers,
        )
    ).status_code == 200
    await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
        processing_job_runner=processing_job_runner,
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    ask_body = ask_response.json()
    assert "PureLink" in ask_body["answer"]
    assert ask_body["citations"]
    citation = ask_body["citations"][0]
    assert citation["chunk_id"] == f"{document_id}:0"
    assert citation["document_id"] == document_id
    assert citation["knowledge_base_id"] == knowledge_base_id
    assert citation["scope"] == "personal"
    assert citation["team_id"] is None
    assert citation["document_name"] == "qa-notes.txt"
    assert citation["source_type"] == "text"
    assert citation["snippet"]
    assert citation["page_number"] is None
    assert citation["section_title"] is None
    assert "internal docs" in citation["text"]

    other_user_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=bob_headers,
        json={"question": "What does PureLink store?"},
    )
    assert other_user_response.status_code == 404


@pytest.mark.anyio
async def test_team_knowledge_base_ask_uses_only_approved_indexed_documents(
    document_client: AsyncClient,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="ask-team-admin@example.com",
        username="ask-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="ask-team-member@example.com",
        username="ask-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="ask-team-outsider@example.com",
        username="ask-team-outsider",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="QA Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="QA Team KB",
    )

    pending_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("qa-pending.md", b"pendingansweronly hidden draft", "text/markdown")},
    )
    assert pending_upload.status_code == 201

    approved_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("qa-approved.md", b"approvedanswer Knowledge base answers for the team.", "text/markdown")},
    )
    assert approved_upload.status_code == 201
    approved_document_id = approved_upload.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/documents/{approved_document_id}/approve",
            headers=admin_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/parse",
            headers=member_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/chunk",
            headers=member_headers,
        )
    ).status_code == 200
    await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/embed",
        headers=member_headers,
        processing_job_runner=processing_job_runner,
    )

    ask_pending = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=member_headers,
        json={"question": "pendingansweronly", "top_k": 5},
    )
    assert ask_pending.status_code == 200
    assert ask_pending.json()["citations"] == []

    ask_approved = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=member_headers,
        json={"question": "What are the answers for the team?", "top_k": 5},
    )
    assert ask_approved.status_code == 200
    approved_body = ask_approved.json()
    assert "Knowledge base answers" in approved_body["answer"]
    assert approved_body["citations"]
    citation = approved_body["citations"][0]
    assert citation["document_id"] == approved_document_id
    assert citation["knowledge_base_id"] == knowledge_base_id
    assert citation["scope"] == "team"
    assert citation["team_id"] == team_id

    outsider_ask = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=outsider_headers,
        json={"question": "What are the answers for the team?"},
    )
    assert outsider_ask.status_code == 404


@pytest.mark.anyio
async def test_personal_knowledge_base_ask_can_use_openai_compatible_provider(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="ask-real-llm@example.com",
        username="ask-real-llm",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Real LLM QA KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("real-qa.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
            headers=alice_headers,
        )
    ).status_code == 200
    await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
        processing_job_runner=processing_job_runner,
    )

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_settings.cache_clear()

    captured_request: dict[str, object] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["json"] = json
        captured_request["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "PureLink stores internal docs for teams. [S1]"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.llm.httpx.post", fake_post)

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    ask_body = ask_response.json()
    assert ask_body["answer"] == "PureLink stores internal docs for teams. [S1]"
    assert ask_body["citations"]
    assert ask_body["citations"][0]["citation_marker"] == "S1"
    assert captured_request["url"] == "https://llm.example/v1/chat/completions"
    assert captured_request["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert captured_request["timeout"] == 30.0
    payload = captured_request["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "test-model"
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "你只能根据给定的 evidence units 回答" in messages[0]["content"]
    assert "每个事实性结论后必须标注来源编号" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "What does PureLink store?" in messages[1]["content"]
    assert "Evidence Units:" in messages[1]["content"]
    assert "[S1]" in messages[1]["content"]
    assert "PureLink stores internal docs for teams." in messages[1]["content"]


@pytest.mark.anyio
async def test_personal_knowledge_base_ask_can_use_deepseek_provider(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="ask-deepseek@example.com",
        username="ask-deepseek",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="DeepSeek QA KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("deepseek-qa.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
            headers=alice_headers,
        )
    ).status_code == 200
    await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
        processing_job_runner=processing_job_runner,
    )

    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")
    monkeypatch.setenv("LLM_THINKING_ENABLED", "true")
    get_settings.cache_clear()

    captured_request: dict[str, object] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["json"] = json
        captured_request["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "PureLink stores internal docs for teams. [S1]"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.llm.httpx.post", fake_post)

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    ask_body = ask_response.json()
    assert ask_body["answer"] == "PureLink stores internal docs for teams. [S1]"
    assert ask_body["citations"]
    assert ask_body["citations"][0]["citation_marker"] == "S1"
    assert captured_request["url"] == "https://api.deepseek.com/chat/completions"
    payload = captured_request["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["reasoning_effort"] == "high"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["stream"] is False
    assert payload["temperature"] == 0
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "你只能根据给定的 evidence units 回答" in messages[0]["content"]
    assert "每个事实性结论后必须标注来源编号" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "What does PureLink store?" in messages[1]["content"]
    assert "Evidence Units:" in messages[1]["content"]
    assert "[S1]" in messages[1]["content"]
    assert "PureLink stores internal docs for teams." in messages[1]["content"]


@pytest.mark.anyio
async def test_personal_ask_creates_and_reuses_conversation_history(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="conversation-personal@example.com",
        username="conversation-personal",
    )
    bob = await _register_and_login(
        document_client,
        email="conversation-personal-other@example.com",
        username="conversation-personal-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Conversation KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("conversation.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    for action in ("parse", "chunk", "embed"):
        response = await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/{action}",
            headers=alice_headers,
        )
        assert response.status_code == 200
        if action == "embed":
            processing_job_runner.run_all()

    first_ask = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?"},
    )
    assert first_ask.status_code == 200
    first_body = first_ask.json()
    conversation_id = first_body["conversation_id"]
    assert isinstance(conversation_id, int)
    assert first_body["citations"]
    assert first_body["citations"][0]["chunk_db_id"] is not None

    second_ask = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={
            "question": "Who is it for?",
            "conversation_id": conversation_id,
        },
    )
    assert second_ask.status_code == 200
    assert second_ask.json()["conversation_id"] == conversation_id

    list_response = await document_client.get(
        "/api/v1/conversations",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    conversations = list_response.json()
    assert len(conversations) == 1
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["knowledge_base_id"] == knowledge_base_id
    assert conversations[0]["scope"] == "personal"
    assert conversations[0]["team_id"] is None
    assert conversations[0]["title"] == "What does PureLink store?"

    detail_response = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=alice_headers,
    )
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["id"] == conversation_id
    assert detail_body["messages"][0]["role"] == "user"
    assert detail_body["messages"][0]["content"] == "What does PureLink store?"
    assert detail_body["messages"][1]["role"] == "assistant"
    assert detail_body["messages"][1]["citations"]
    assert detail_body["messages"][1]["citations"][0]["document_id"] == document_id
    assert detail_body["messages"][1]["citations"][0]["chunk_db_id"] is not None
    assert detail_body["messages"][2]["role"] == "user"
    assert detail_body["messages"][2]["content"] == "Who is it for?"
    assert detail_body["messages"][3]["role"] == "assistant"

    with test_session_factory() as db:
        live_units = list(
            db.scalars(
                select(DocumentCitationUnit).where(DocumentCitationUnit.document_id == document_id)
            )
        )
        assert live_units
        for item in live_units:
            db.delete(item)
        db.commit()

    snapshot_after_delete = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=alice_headers,
    )
    assert snapshot_after_delete.status_code == 200
    snapshot_body = snapshot_after_delete.json()
    assert snapshot_body["messages"][1]["citations"]
    assert snapshot_body["messages"][1]["citations"][0]["snippet"]
    assert snapshot_body["messages"][1]["citations"][0]["chunk_id"] == f"{document_id}:0"
    assert snapshot_body["messages"][1]["citations"][0]["chunk_db_id"] is not None

    other_user_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=bob_headers,
    )
    assert other_user_detail.status_code == 404


@pytest.mark.anyio
async def test_team_conversation_history_is_user_owned_and_team_scoped(
    document_client: AsyncClient,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="conversation-team-admin@example.com",
        username="conversation-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="conversation-team-member@example.com",
        username="conversation-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="conversation-team-outsider@example.com",
        username="conversation-team-outsider",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Conversation Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Team Conversation KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("team-conversation.md", b"Team answers are shared after approval.", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    for action in ("parse", "chunk", "embed"):
        response = await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/{action}",
            headers=member_headers,
        )
        assert response.status_code == 200
        if action == "embed":
            processing_job_runner.run_all()

    ask_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=member_headers,
        json={"question": "What happens after approval?"},
    )
    assert ask_response.status_code == 200
    conversation_id = ask_response.json()["conversation_id"]

    member_list = await document_client.get(
        "/api/v1/conversations",
        headers=member_headers,
    )
    assert member_list.status_code == 200
    member_conversations = member_list.json()
    assert len(member_conversations) == 1
    assert member_conversations[0]["id"] == conversation_id
    assert member_conversations[0]["scope"] == "team"
    assert member_conversations[0]["team_id"] == team_id

    member_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=member_headers,
    )
    assert member_detail.status_code == 200
    member_messages = member_detail.json()["messages"]
    assert len(member_messages) == 2
    assert member_messages[1]["citations"]
    assert member_messages[1]["citations"][0]["document_id"] == document_id
    assert member_messages[1]["citations"][0]["team_id"] == team_id

    admin_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=admin_headers,
    )
    outsider_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=outsider_headers,
    )
    assert admin_detail.status_code == 404
    assert outsider_detail.status_code == 404


@pytest.mark.anyio
async def test_personal_txt_process_endpoint_marks_ready_creates_chunks_and_supports_retrieval(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-ready@example.com",
        username="txt-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "ready-notes.txt",
                b"PureLink stores product notes for the team workspace.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    process_body = process_response.json()
    assert process_body["document_id"] == document_id
    assert process_body["document_status"] == "processing"
    assert process_body["job_status"] == "queued"
    assert process_body["trigger_type"] == "process"
    assert process_body["attempt_number"] == 1

    with test_session_factory() as db:
        queued_document = db.get(Document, document_id)
        assert queued_document is not None
        assert queued_document.processing_status == DocumentProcessingStatus.PROCESSING
        queued_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
        queued_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(queued_jobs) == 1
    assert queued_jobs[0].status == ProcessingJobStatus.QUEUED
    assert queued_chunks == []

    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.READY
        assert saved_document.error_message is None
        assert saved_document.processed_at is not None
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_jobs) == 2
    assert saved_jobs[0].triggered_by_id == alice["user_id"]
    assert saved_jobs[0].job_type == ProcessingJobType.DOCUMENT_PROCESS
    assert saved_jobs[0].trigger_type == ProcessingJobTrigger.PROCESS
    assert saved_jobs[0].status == ProcessingJobStatus.SUCCEEDED
    assert saved_jobs[0].current_step == "completed"
    assert saved_jobs[0].attempt_number == 1
    assert saved_jobs[0].retry_count == 0
    assert saved_jobs[0].max_retries == 3
    assert saved_jobs[0].worker_name == processing_worker_service.REDIS_PROCESSING_WORKER_NAME
    assert saved_jobs[0].locked_by == processing_worker_service.REDIS_PROCESSING_WORKER_NAME
    assert saved_jobs[0].started_at is not None
    assert saved_jobs[0].finished_at is not None
    assert saved_jobs[0].locked_at is not None
    assert saved_jobs[0].timeout_at is not None
    assert saved_jobs[1].job_type == ProcessingJobType.DOCUMENT_INDEX
    assert saved_jobs[1].trigger_type == ProcessingJobTrigger.INDEX
    assert saved_jobs[1].status == ProcessingJobStatus.QUEUED
    assert saved_jobs[1].attempt_number == 1

    assert len(saved_chunks) == 1
    assert saved_chunks[0].chunk_key == f"{document_id}:0"
    assert "PureLink stores product notes" in saved_chunks[0].chunk_text

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "ready"

    processing_job_runner.run_all()

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "product notes", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["results"]
    assert retrieve_body["results"][0]["document_id"] == document_id
    assert retrieve_body["results"][0]["chunk_id"] == f"{document_id}:0"
    assert retrieve_body["results"][0]["document_name"] == "ready-notes.txt"
    assert retrieve_body["results"][0]["source_type"] == "text"
    assert retrieve_body["results"][0]["snippet"]
    assert "product notes" in retrieve_body["results"][0]["text"]

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    ask_body = ask_response.json()
    assert ask_body["citations"]
    assert ask_body["citations"][0]["chunk_id"] == f"{document_id}:0"
    assert ask_body["citations"][0]["document_name"] == "ready-notes.txt"
    assert ask_body["citations"][0]["source_type"] == "text"
    assert ask_body["citations"][0]["snippet"]

    preview_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/preview",
        headers=alice_headers,
    )
    assert preview_response.status_code == 200
    preview_body = preview_response.json()
    assert preview_body["document"]["id"] == document_id
    assert preview_body["chunks"][0]["chunk_id"] == f"{document_id}:0"
    assert preview_body["chunks"][0]["source_locator"]["kind"] == "text_range"
    assert preview_body["chunks"][0]["preview_target"]["locator_kind"] == "text_range"

    file_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/file",
        headers=alice_headers,
    )
    assert file_response.status_code == 200
    assert file_response.content == b"PureLink stores product notes for the team workspace."


@pytest.mark.anyio
async def test_personal_txt_process_failure_marks_document_failed_and_records_error(
    document_client: AsyncClient,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-failure@example.com",
        username="txt-process-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("missing-source.txt", b"source will be removed", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_body = upload_response.json()
    document_id = document_body["id"]

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    assert saved_file.exists()
    saved_file.unlink()

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    process_body = process_response.json()
    assert process_body["document_id"] == document_id
    assert process_body["document_status"] == "processing"
    assert process_body["job_status"] == "queued"

    processing_job_runner.run_all()

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    listed_document = list_response.json()[0]
    assert listed_document["processing_status"] == "failed"
    assert listed_document["error_message"] == "Document source file does not exist."
    assert listed_document["processed_at"] is None
    assert listed_document["latest_processing_job_status"] == "failed"
    assert listed_document["latest_processing_job_trigger"] == "process"
    assert listed_document["latest_processing_job_attempt_number"] == 1

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.FAILED
        assert saved_document.error_message == "Document source file does not exist."
        assert saved_document.processed_at is None
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )

    assert len(saved_jobs) == 1
    assert saved_jobs[0].status == ProcessingJobStatus.FAILED
    assert saved_jobs[0].trigger_type == ProcessingJobTrigger.PROCESS
    assert saved_jobs[0].error_message == "Document source file does not exist."
    assert saved_jobs[0].finished_at is not None
    assert saved_chunks == []


@pytest.mark.anyio
async def test_personal_txt_process_sets_processing_before_ready(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-transition-ready@example.com",
        username="txt-process-transition-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Transition Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("transition-ready.txt", b"Transition to ready.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    seen_statuses: list[DocumentProcessingStatus] = []

    def assert_processing_then_extract(*, source_path: Path):
        with test_session_factory() as db:
            saved_document = db.get(Document, document_id)
            assert saved_document is not None
            seen_statuses.append(saved_document.processing_status)
        return extract_text_from_txt(source_path=source_path)

    monkeypatch.setattr(
        "app.services.document_processing.extract_text_from_txt",
        assert_processing_then_extract,
    )

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["document_status"] == "processing"
    assert seen_statuses == []
    processing_job_runner.run_all()
    assert seen_statuses == [DocumentProcessingStatus.PROCESSING]


@pytest.mark.anyio
async def test_personal_txt_process_sets_job_processing_before_extract(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-job-processing@example.com",
        username="txt-process-job-processing",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Job Processing KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("job-processing.txt", b"Check processing job status.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    seen_job_statuses: list[ProcessingJobStatus] = []

    def assert_job_processing_then_extract(*, source_path: Path):
        with test_session_factory() as db:
            current_job = db.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.desc())
            )
            assert current_job is not None
            seen_job_statuses.append(current_job.status)
        return extract_text_from_txt(source_path=source_path)

    monkeypatch.setattr(
        "app.services.document_processing.extract_text_from_txt",
        assert_job_processing_then_extract,
    )

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    assert seen_job_statuses == [ProcessingJobStatus.PROCESSING]


@pytest.mark.anyio
async def test_personal_txt_process_sets_processing_before_failed(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-transition-failed@example.com",
        username="txt-process-transition-failed",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Transition Failed KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("transition-failed.txt", b"Transition to failed.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    seen_statuses: list[DocumentProcessingStatus] = []

    def assert_processing_then_fail(*, source_path: Path):
        with test_session_factory() as db:
            saved_document = db.get(Document, document_id)
            assert saved_document is not None
            seen_statuses.append(saved_document.processing_status)
        raise DocumentProcessingError("Simulated txt processing failure.")

    monkeypatch.setattr(
        "app.services.document_processing.extract_text_from_txt",
        assert_processing_then_fail,
    )

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["document_status"] == "processing"
    assert seen_statuses == []

    processing_job_runner.run_all()
    assert seen_statuses == [DocumentProcessingStatus.PROCESSING]

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    listed_document = list_response.json()[0]
    assert listed_document["processing_status"] == "failed"
    assert listed_document["error_message"] == "Simulated txt processing failure."


@pytest.mark.anyio
async def test_personal_process_submission_rejects_duplicate_active_job(
    document_client: AsyncClient,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-duplicate@example.com",
        username="txt-process-duplicate",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Duplicate KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("duplicate.txt", b"Duplicate processing protection.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    first_process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert first_process_response.status_code == 200
    assert first_process_response.json()["job_status"] == "queued"

    duplicate_process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert duplicate_process_response.status_code == 200
    assert duplicate_process_response.json()["job_id"] == first_process_response.json()["job_id"]

    processing_job_runner.run_all()


@pytest.mark.anyio
async def test_processing_job_acquire_only_claims_queued_job(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-claim@example.com",
        username="txt-process-claim",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Claim KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("claim.txt", b"Only one worker should claim this job.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    job_id = process_response.json()["job_id"]

    with test_session_factory() as db:
        claimed_job = acquire_processing_job(
            db,
            job_id=job_id,
            worker_name="worker-one",
            timeout_seconds=30,
        )
        second_claim = acquire_processing_job(
            db,
            job_id=job_id,
            worker_name="worker-two",
            timeout_seconds=30,
        )
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert claimed_job is not None
    assert claimed_job.status == ProcessingJobStatus.PROCESSING
    assert claimed_job.worker_name == "worker-one"
    assert claimed_job.locked_by == "worker-one"
    assert claimed_job.started_at is not None
    assert claimed_job.locked_at is not None
    assert claimed_job.timeout_at is not None
    assert second_claim is None
    assert len(saved_jobs) == 1
    assert saved_jobs[0].status == ProcessingJobStatus.PROCESSING

    duplicate_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["job_id"] == job_id

    processing_job_runner.submissions.clear()


@pytest.mark.anyio
async def test_processing_job_timeout_marks_job_and_document_failed(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-timeout@example.com",
        username="txt-process-timeout",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Timeout KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("timeout.txt", b"Timeout should fail this job.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    job_id = process_response.json()["job_id"]

    with test_session_factory() as db:
        claimed_job = acquire_processing_job(
            db,
            job_id=job_id,
            worker_name="timeout-worker",
            timeout_seconds=1,
        )
        assert claimed_job is not None
        assert claimed_job.timeout_at is not None
        timeout_count = fail_timed_out_processing_jobs(
            db,
            now=claimed_job.timeout_at + timedelta(seconds=1),
            timeout_seconds=1,
        )
        timed_out_document = db.get(Document, document_id)
        timed_out_job = db.get(ProcessingJob, job_id)

    assert timeout_count == 1
    assert timed_out_document is not None
    assert timed_out_document.processing_status == DocumentProcessingStatus.FAILED
    assert timed_out_document.error_message == "Processing job timed out."
    assert timed_out_job is not None
    assert timed_out_job.status == ProcessingJobStatus.FAILED
    assert timed_out_job.error_code == "JOB_TIMEOUT"
    assert timed_out_job.finished_at is not None

    processing_job_runner.submissions.clear()


@pytest.mark.anyio
async def test_retryable_processing_error_requeues_same_job_then_succeeds(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-auto-retry@example.com",
        username="txt-process-auto-retry",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Auto Retry KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("auto-retry.txt", b"Retryable text eventually succeeds.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    call_count = 0

    def flaky_extract_text_from_txt(*, source_path: Path):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise DocumentProcessingError(
                "Temporary chunk persistence failure.",
                error_code="CHUNK_PERSIST_FAILED",
            )
        return extract_text_from_txt(source_path=source_path)

    monkeypatch.setattr(
        "app.services.document_processing.extract_text_from_txt",
        flaky_extract_text_from_txt,
    )

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    job_id = process_response.json()["job_id"]

    processing_job_runner.run_all()

    with test_session_factory() as db:
        retried_job = db.get(ProcessingJob, job_id)
        retried_document = db.get(Document, document_id)

    assert retried_job is not None
    assert retried_job.status == ProcessingJobStatus.QUEUED
    assert retried_job.retry_count == 1
    assert retried_job.error_code == "CHUNK_PERSIST_FAILED"
    assert retried_document is not None
    assert retried_document.processing_status == DocumentProcessingStatus.PROCESSING
    assert len(processing_job_runner.submissions) == 1

    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
        saved_document = db.get(Document, document_id)

    assert call_count == 2
    assert saved_document is not None
    assert saved_document.processing_status == DocumentProcessingStatus.READY
    assert saved_jobs[0].id == job_id
    assert saved_jobs[0].status == ProcessingJobStatus.SUCCEEDED
    assert saved_jobs[0].retry_count == 1
    assert saved_jobs[0].error_code is None
    assert saved_jobs[0].started_at is not None
    assert saved_jobs[0].finished_at is not None
    assert saved_jobs[1].job_type == ProcessingJobType.DOCUMENT_INDEX
    assert saved_jobs[1].status == ProcessingJobStatus.QUEUED


@pytest.mark.anyio
async def test_personal_txt_process_sanitizes_nul_before_persisting_chunks(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-nul@example.com",
        username="txt-process-nul",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT NUL Sanitizer KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("nul.txt", b"alpha\x00 beta remains readable", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_chunk = db.scalar(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

    assert saved_chunk is not None
    assert "\x00" not in saved_chunk.chunk_text
    assert "alpha beta remains readable" in saved_chunk.chunk_text


@pytest.mark.anyio
async def test_personal_process_submission_failure_leaves_queued_job_when_queue_unavailable(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-queue-down@example.com",
        username="txt-process-queue-down",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Process Queue Down KB",
    )

    def fail_submit_processing_job(*, job: ProcessingJob) -> str:
        raise RuntimeError("Redis queue is unavailable.")

    monkeypatch.setattr(
        processing_worker_service,
        "submit_processing_job",
        fail_submit_processing_job,
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("queue-down.txt", b"Queue failure should not fallback.", "text/plain")},
    )
    assert upload_response.status_code == 500
    assert "remains queued" in upload_response.json()["detail"]

    with test_session_factory() as db:
        saved_document = db.scalar(
            select(Document).where(Document.original_filename == "queue-down.txt")
        )
        assert saved_document is not None
        document_id = saved_document.id
        assert saved_document.processing_status == DocumentProcessingStatus.PROCESSING
        assert saved_document.error_message is None
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_jobs) == 1
    assert saved_jobs[0].status == ProcessingJobStatus.QUEUED
    assert saved_jobs[0].job_type == ProcessingJobType.DOCUMENT_PROCESS
    assert saved_jobs[0].error_message is None
    assert saved_chunks == []


@pytest.mark.anyio
async def test_personal_failed_document_can_retry_via_processing_job(
    document_client: AsyncClient,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-retry@example.com",
        username="txt-process-retry",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Retry KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("retry-notes.txt", b"retry source text", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_body = upload_response.json()
    document_id = document_body["id"]

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    saved_file.unlink()

    failed_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert failed_response.status_code == 200
    assert failed_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    saved_file.write_bytes(b"PureLink retry succeeds after the file is restored.")

    retry_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/retry-process",
        headers=alice_headers,
    )
    assert retry_response.status_code == 200
    retry_body = retry_response.json()
    assert retry_body["document_id"] == document_id
    assert retry_body["trigger_type"] == "retry"
    assert retry_body["document_status"] == "processing"
    assert retry_body["job_status"] == "queued"
    assert retry_body["attempt_number"] == 2

    processing_job_runner.run_all()

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    listed_document = list_response.json()[0]
    assert listed_document["processing_status"] == "ready"
    assert listed_document["latest_processing_job_status"] == "queued"
    assert listed_document["latest_processing_job_trigger"] == "index"
    assert listed_document["latest_processing_job_attempt_number"] == 1

    jobs_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/processing-jobs",
        headers=alice_headers,
    )
    assert jobs_response.status_code == 200
    jobs_body = jobs_response.json()
    assert [job["trigger_type"] for job in jobs_body] == ["index", "retry", "process"]

    latest_job_id = jobs_body[1]["id"]
    latest_job_detail = await document_client.get(
        f"/api/v1/processing-jobs/{latest_job_id}",
        headers=alice_headers,
    )
    assert latest_job_detail.status_code == 200
    assert latest_job_detail.json()["status"] == "succeeded"
    assert (
        latest_job_detail.json()["worker_name"]
        == processing_worker_service.REDIS_PROCESSING_WORKER_NAME
    )

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.READY
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_jobs) == 3
    assert saved_jobs[0].status == ProcessingJobStatus.FAILED
    assert saved_jobs[1].status == ProcessingJobStatus.SUCCEEDED
    assert saved_jobs[1].job_type == ProcessingJobType.DOCUMENT_PROCESS
    assert saved_jobs[1].trigger_type == ProcessingJobTrigger.RETRY
    assert saved_jobs[1].previous_job_id == saved_jobs[0].id
    assert saved_jobs[1].attempt_number == 2
    assert saved_jobs[2].job_type == ProcessingJobType.DOCUMENT_INDEX
    assert saved_jobs[2].status == ProcessingJobStatus.QUEUED
    assert len(saved_chunks) == 1
    assert "retry succeeds" in saved_chunks[0].chunk_text


@pytest.mark.anyio
async def test_personal_ready_document_can_reprocess_and_replace_chunks(
    document_client: AsyncClient,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="txt-process-reprocess@example.com",
        username="txt-process-reprocess",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="TXT Reprocess KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("reprocess-notes.txt", b"PureLink initial reprocess content.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_body = upload_response.json()
    document_id = document_body["id"]

    first_process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert first_process_response.status_code == 200
    assert first_process_response.json()["job_status"] == "queued"
    processing_job_runner.run_all()
    processing_job_runner.run_all()

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    saved_file.write_bytes(b"PureLink reprocessed content replaces the old chunk.")

    reprocess_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/reprocess",
        headers=alice_headers,
    )
    assert reprocess_response.status_code == 200
    reprocess_body = reprocess_response.json()
    assert reprocess_body["trigger_type"] == "reprocess"
    assert reprocess_body["job_status"] == "queued"
    assert reprocess_body["attempt_number"] == 2

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "reprocessed content", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["results"]
    assert "reprocessed content replaces" in retrieve_body["results"][0]["text"]

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.INDEXED
        saved_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_jobs) == 4
    assert saved_jobs[0].trigger_type == ProcessingJobTrigger.PROCESS
    assert saved_jobs[1].trigger_type == ProcessingJobTrigger.INDEX
    assert saved_jobs[1].status == ProcessingJobStatus.SUCCEEDED
    assert saved_jobs[2].trigger_type == ProcessingJobTrigger.REPROCESS
    assert saved_jobs[2].status == ProcessingJobStatus.SUCCEEDED
    assert saved_jobs[2].previous_job_id == saved_jobs[0].id
    assert saved_jobs[3].trigger_type == ProcessingJobTrigger.INDEX
    assert saved_jobs[3].status == ProcessingJobStatus.SUCCEEDED
    assert len(saved_chunks) == 1
    assert saved_chunks[0].chunk_text == "PureLink reprocessed content replaces the old chunk."

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        index_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.document_id == document_id,
                    ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
                )
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert [job.status for job in index_jobs] == [
        ProcessingJobStatus.SUCCEEDED,
        ProcessingJobStatus.SUCCEEDED,
    ]

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    indexed_document_payload = next(
        item for item in index_payload["documents"] if item["document_id"] == document_id
    )
    assert indexed_document_payload["chunks"][0]["text"] == (
        "PureLink reprocessed content replaces the old chunk."
    )


@pytest.mark.anyio
async def test_personal_markdown_process_endpoint_marks_ready_creates_chunks_and_supports_retrieval(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="md-process-ready@example.com",
        username="md-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Markdown Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "release-notes.md",
                b"# Release Notes\n\nPureLink keeps markdown notes searchable for the team.",
                "text/markdown",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 1
    metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    assert metadata["source_type"] == "markdown"
    assert metadata["section_title"] == "Release Notes"
    assert metadata["heading_path"] == ["Release Notes"]
    assert metadata["source_locator"] == "heading:Release Notes"
    assert "markdown notes searchable" in saved_chunks[0].chunk_text

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "markdown notes", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["results"]
    assert retrieve_body["results"][0]["document_id"] == document_id
    assert retrieve_body["results"][0]["document_name"] == "release-notes.md"
    assert retrieve_body["results"][0]["source_type"] == "markdown"
    assert retrieve_body["results"][0]["section_title"] == "Release Notes"
    _assert_api_source_locator(
        retrieve_body["results"][0]["source_locator"],
        kind="text_range",
        source_locator_text="heading:Release Notes",
        section_title="Release Notes",
    )
    assert retrieve_body["results"][0]["heading_path"] == ["Release Notes"]

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink keep searchable?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    citation = ask_response.json()["citations"][0]
    assert citation["document_name"] == "release-notes.md"
    assert citation["source_type"] == "markdown"
    assert citation["section_title"] == "Release Notes"
    _assert_api_source_locator(
        citation["source_locator"],
        kind="text_range",
        source_locator_text="heading:Release Notes",
        section_title="Release Notes",
    )


@pytest.mark.anyio
async def test_personal_pdf_process_endpoint_marks_ready_and_preserves_page_metadata(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    def fail_if_pdf_ocr_used(*, source_path: Path, **kwargs) -> None:
        raise AssertionError("Text PDF should not fallback to scanned PDF OCR.")

    monkeypatch.setattr(
        "app.services.document_processing.extract_text_from_scanned_pdf",
        fail_if_pdf_ocr_used,
    )

    alice = await _register_and_login(
        document_client,
        email="pdf-process-ready@example.com",
        username="pdf-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="PDF Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "manual.pdf",
                _build_minimal_pdf(text="PureLink PDF manuals stay searchable."),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 1
    metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    assert metadata["source_type"] == "pdf"
    assert metadata["page_number"] == 1
    assert metadata["source_locator"] == "page:1"
    assert metadata["extractor"] == "pymupdf"
    assert "PDF manuals stay searchable" in saved_chunks[0].chunk_text

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "PDF manuals", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    pdf_result = retrieve_response.json()["results"][0]
    assert pdf_result["document_id"] == document_id
    assert pdf_result["document_name"] == "manual.pdf"
    assert pdf_result["source_type"] == "pdf"
    assert pdf_result["page_number"] == 1
    _assert_api_source_locator(
        pdf_result["source_locator"],
        kind="pdf_page",
        source_locator_text="page:1",
        page_number=1,
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What stays searchable in the PDF?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    pdf_citation = ask_response.json()["citations"][0]
    assert pdf_citation["document_name"] == "manual.pdf"
    assert pdf_citation["source_type"] == "pdf"
    assert pdf_citation["page_number"] == 1
    _assert_api_source_locator(
        pdf_citation["source_locator"],
        kind="pdf_page",
        source_locator_text="page:1",
        page_number=1,
    )


@pytest.mark.anyio
async def test_personal_pdf_garbled_direct_text_falls_back_to_ocr(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_pdf_page_segments_with_pymupdf",
        lambda *, source_path: (
            [
                ExtractedTextSegment(
                    text="\x0f\x02\x03" * 20,
                    metadata={
                        "source_type": "pdf",
                        "page_number": 1,
                        "source_locator": "page:1",
                        "extractor": "pymupdf",
                    },
                )
            ],
            1,
            "pymupdf",
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=["OCR fallback text"],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(
            result=OCRResult(
                text="OCR fallback recovered readable PDF text.",
                provider_name="fake_ocr",
                provider_version="fake-v1",
                language="eng",
                confidence=92.0,
                regions=(),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="pdf-garbled-fallback@example.com",
        username="pdf-garbled-fallback",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="PDF Garbled Fallback KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "garbled.pdf",
                _build_minimal_pdf(text="placeholder"),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        saved_chunk = db.scalar(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        succeeded_job = db.scalar(
            select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        )

    assert saved_chunk is not None
    assert "OCR fallback recovered readable PDF text" in saved_chunk.chunk_text
    metadata = json.loads(saved_chunk.metadata_json or "{}")
    assert metadata["source_type"] == "pdf"
    assert metadata["page_number"] == 1
    assert metadata["source_locator"] == "page:1"
    assert metadata["extractor"] == "ocr_pdf:fake_ocr"
    assert "\x00" not in saved_chunk.chunk_text
    assert succeeded_job is not None
    assert succeeded_job.status == ProcessingJobStatus.SUCCEEDED


@pytest.mark.anyio
async def test_personal_pdf_garbled_direct_text_reports_ocr_unavailable(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_pdf_page_segments_with_pymupdf",
        lambda *, source_path: (
            [
                ExtractedTextSegment(
                    text="\x00\x0f\x02" * 20,
                    metadata={
                        "source_type": "pdf",
                        "page_number": 1,
                        "source_locator": "page:1",
                        "extractor": "pymupdf",
                    },
                )
            ],
            1,
            "pymupdf",
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=["OCR unavailable page"],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: (_ for _ in ()).throw(OCRProviderError("OCR provider missing.")),
    )

    alice = await _register_and_login(
        document_client,
        email="pdf-ocr-unavailable@example.com",
        username="pdf-ocr-unavailable",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="PDF OCR Unavailable KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "ocr-unavailable.pdf",
                _build_minimal_pdf(text="placeholder"),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_document = db.get(Document, document_id)
        assert failed_document is not None
        assert failed_document.processing_status == DocumentProcessingStatus.FAILED
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )
        failed_job = db.scalar(
            select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        )
        latest_error_code = failed_document.latest_processing_job_error_code

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.current_step == "extract_text"
    assert failed_job.error_code == "OCR_PROVIDER_UNAVAILABLE"
    assert failed_job.retry_count == 0
    assert failed_job.finished_at is not None
    assert latest_error_code == "OCR_PROVIDER_UNAVAILABLE"


@pytest.mark.anyio
async def test_personal_pdf_garbled_direct_text_reports_ocr_no_text_found(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_pdf_page_segments_with_pymupdf",
        lambda *, source_path: (
            [
                ExtractedTextSegment(
                    text="\x0f\x02\x03" * 20,
                    metadata={
                        "source_type": "pdf",
                        "page_number": 1,
                        "source_locator": "page:1",
                        "extractor": "pymupdf",
                    },
                )
            ],
            1,
            "pymupdf",
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=["blank OCR page"],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(
            result=OCRResult(
                text="",
                provider_name="fake_ocr",
                provider_version="fake-v1",
                language="eng",
                confidence=0.0,
                regions=(),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="pdf-ocr-no-text@example.com",
        username="pdf-ocr-no-text",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="PDF OCR No Text KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "ocr-no-text.pdf",
                _build_minimal_pdf(text="placeholder"),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_job = db.scalar(
            select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        )
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.error_code == "OCR_NO_TEXT_FOUND"
    assert failed_job.retry_count == 0


@pytest.mark.anyio
async def test_personal_scanned_pdf_process_uses_ocr_and_preserves_page_metadata(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=[
                "Scanned PDF page one",
                "Scanned PDF page two mentions OCR citations",
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: SequentialOCRProvider(
            results=[
                OCRResult(
                    text="Scanned PDF onboarding page.",
                    provider_name="fake_ocr",
                    provider_version="fake-v1",
                    language="eng",
                    confidence=95.0,
                    regions=(
                        OCRRegion(
                            text="Scanned PDF onboarding page.",
                            left=18,
                            top=20,
                            width=340,
                            height=28,
                            confidence=95.0,
                        ),
                    ),
                ),
                OCRResult(
                    text="Scanned PDF page two keeps OCR citations searchable.",
                    provider_name="fake_ocr",
                    provider_version="fake-v1",
                    language="eng",
                    confidence=96.0,
                    regions=(
                        OCRRegion(
                            text="Scanned PDF page two keeps OCR citations searchable.",
                            left=18,
                            top=20,
                            width=460,
                            height=28,
                            confidence=96.0,
                        ),
                    ),
                ),
            ]
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="scanned-pdf-process-ready@example.com",
        username="scanned-pdf-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Scanned PDF Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "scanner-capture.pdf",
                _build_scanned_pdf_bytes(
                    page_texts=[
                        "Scanned PDF page one",
                        "Scanned PDF page two mentions OCR citations",
                    ]
                ),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 2
    first_chunk_metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    second_chunk_metadata = json.loads(saved_chunks[1].metadata_json or "{}")
    assert first_chunk_metadata["source_type"] == "pdf"
    assert first_chunk_metadata["page_number"] == 1
    assert first_chunk_metadata["source_locator"] == "page:1"
    assert first_chunk_metadata["ocr_provider"] == "fake_ocr"
    assert second_chunk_metadata["source_type"] == "pdf"
    assert second_chunk_metadata["page_number"] == 2
    assert second_chunk_metadata["source_locator"] == "page:2"
    assert "OCR citations searchable" in saved_chunks[1].chunk_text

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "OCR citations searchable", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    pdf_result = retrieve_response.json()["results"][0]
    assert pdf_result["document_id"] == document_id
    assert pdf_result["document_name"] == "scanner-capture.pdf"
    assert pdf_result["source_type"] == "pdf"
    assert pdf_result["page_number"] == 2
    _assert_api_source_locator(
        pdf_result["source_locator"],
        kind="pdf_page",
        source_locator_text="page:2",
        page_number=2,
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "Which scanned page keeps OCR citations searchable?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    pdf_citation = ask_response.json()["citations"][0]
    assert pdf_citation["document_name"] == "scanner-capture.pdf"
    assert pdf_citation["source_type"] == "pdf"
    assert pdf_citation["page_number"] == 2
    _assert_api_source_locator(
        pdf_citation["source_locator"],
        kind="pdf_page",
        source_locator_text="page:2",
        page_number=2,
    )


@pytest.mark.anyio
async def test_personal_scanned_pdf_document_auto_upgrades_to_indexed_after_process(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=["Scanned PDF indexing page"],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: SequentialOCRProvider(
            results=[
                OCRResult(
                    text="Scanned PDF indexing stays searchable after OCR.",
                    provider_name="fake_ocr",
                    provider_version="fake-v2",
                    language="eng",
                    confidence=94.0,
                    regions=(
                        OCRRegion(
                            text="Scanned PDF indexing stays searchable after OCR.",
                            left=22,
                            top=26,
                            width=430,
                            height=28,
                            confidence=94.0,
                        ),
                    ),
                )
            ]
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="scanned-pdf-indexed@example.com",
        username="scanned-pdf-indexed",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Scanned PDF Indexed KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "scanned-indexed.pdf",
                _build_scanned_pdf_bytes(page_texts=["Scanned PDF indexing page"]),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert [job.job_type for job in jobs] == [
        ProcessingJobType.DOCUMENT_PROCESS,
        ProcessingJobType.DOCUMENT_INDEX,
    ]
    assert [job.status for job in jobs] == [
        ProcessingJobStatus.SUCCEEDED,
        ProcessingJobStatus.SUCCEEDED,
    ]

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    indexed_chunk = index_payload["documents"][0]["chunks"][0]
    assert indexed_chunk["metadata"]["source_type"] == "pdf"
    assert indexed_chunk["metadata"]["page_number"] == 1
    assert indexed_chunk["metadata"]["source_locator"] == "page:1"
    assert indexed_chunk["metadata"]["ocr_provider"] == "fake_ocr"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "searchable after OCR", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["document_id"] == document_id
    assert retrieve_response.json()["results"][0]["source_type"] == "pdf"
    assert retrieve_response.json()["results"][0]["page_number"] == 1


@pytest.mark.anyio
async def test_personal_scanned_pdf_process_failure_marks_document_failed_for_ocr_error(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=["Broken scanned PDF OCR page"],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(error=OCRProviderError("Simulated scanned PDF OCR failure.")),
    )

    alice = await _register_and_login(
        document_client,
        email="scanned-pdf-ocr-failure@example.com",
        username="scanned-pdf-ocr-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Scanned PDF OCR Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "broken-scanned.pdf",
                _build_scanned_pdf_bytes(page_texts=["Broken scanned PDF OCR page"]),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_document = db.get(Document, document_id)
        assert failed_document is not None
        assert failed_document.processing_status == DocumentProcessingStatus.FAILED
        assert failed_document.error_message == "Simulated scanned PDF OCR failure."
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )
        failed_job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.error_message == "Simulated scanned PDF OCR failure."
    assert failed_job.error_code == "OCR_PROVIDER_UNAVAILABLE"


@pytest.mark.anyio
async def test_personal_scanned_pdf_index_failure_keeps_document_ready_and_retrieval_fallback(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: _fake_rendered_pdf_pages(
            output_dir=output_dir,
            page_texts=["Scanned fallback page"],
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: SequentialOCRProvider(
            results=[
                OCRResult(
                    text="Scanned PDF fallback keeps retrieval available.",
                    provider_name="fake_ocr",
                    provider_version="fake-v3",
                    language="eng",
                    confidence=93.0,
                    regions=(
                        OCRRegion(
                            text="Scanned PDF fallback keeps retrieval available.",
                            left=16,
                            top=24,
                            width=420,
                            height=26,
                            confidence=93.0,
                        ),
                    ),
                )
            ]
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="scanned-pdf-index-failure@example.com",
        username="scanned-pdf-index-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Scanned PDF Index Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "scanned-fallback.pdf",
                _build_scanned_pdf_bytes(page_texts=["Scanned fallback page"]),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    def fail_embed_ready(*args, **kwargs):
        raise DocumentEmbeddingError("Simulated scanned PDF indexing failure.")

    monkeypatch.setattr(
        document_indexing_service,
        "embed_ready_document_chunks",
        fail_embed_ready,
    )
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        failed_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_index_job is not None
        assert failed_index_job.status == ProcessingJobStatus.FAILED
        assert failed_index_job.error_message == "Simulated scanned PDF indexing failure."

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "retrieval available", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["document_id"] == document_id
    assert retrieve_response.json()["results"][0]["source_type"] == "pdf"
    assert retrieve_response.json()["results"][0]["page_number"] == 1

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What remains available after scanned PDF indexing fails?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    pdf_citation = ask_response.json()["citations"][0]
    assert pdf_citation["document_id"] == document_id
    assert pdf_citation["source_type"] == "pdf"
    assert pdf_citation["page_number"] == 1
    _assert_api_source_locator(
        pdf_citation["source_locator"],
        kind="pdf_page",
        source_locator_text="page:1",
        page_number=1,
    )


@pytest.mark.anyio
async def test_personal_docx_process_endpoint_marks_ready_and_preserves_section_metadata(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="docx-process-ready@example.com",
        username="docx-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="DOCX Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "architecture.docx",
                _build_minimal_docx(
                    paragraphs=[
                        ("Architecture", "Heading1"),
                        ("PureLink keeps docx knowledge organized and searchable.", None),
                    ]
                ),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 1
    metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    assert metadata["source_type"] == "docx"
    assert metadata["section_title"] == "Architecture"
    assert metadata["heading_path"] == ["Architecture"]
    assert metadata["source_locator"] == "section:Architecture"
    assert "docx knowledge organized" in saved_chunks[0].chunk_text

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "docx knowledge", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    docx_result = retrieve_response.json()["results"][0]
    assert docx_result["document_id"] == document_id
    assert docx_result["document_name"] == "architecture.docx"
    assert docx_result["source_type"] == "docx"
    assert docx_result["section_title"] == "Architecture"
    _assert_api_source_locator(
        docx_result["source_locator"],
        kind="text_range",
        source_locator_text="section:Architecture",
        section_title="Architecture",
    )
    assert docx_result["heading_path"] == ["Architecture"]

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does the architecture doc say?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    docx_citation = ask_response.json()["citations"][0]
    assert docx_citation["document_name"] == "architecture.docx"
    assert docx_citation["source_type"] == "docx"
    assert docx_citation["section_title"] == "Architecture"
    _assert_api_source_locator(
        docx_citation["source_locator"],
        kind="text_range",
        source_locator_text="section:Architecture",
        section_title="Architecture",
    )


@pytest.mark.anyio
async def test_personal_image_process_endpoint_marks_ready_creates_chunks_and_supports_retrieval(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(
            result=OCRResult(
                text="PureLink image notes stay searchable.\nImage citations stay stable.",
                provider_name="fake_ocr",
                provider_version="fake-v1",
                language="eng",
                confidence=96.5,
                regions=(
                    OCRRegion(
                        text="PureLink image notes stay searchable.",
                        left=12,
                        top=18,
                        width=320,
                        height=24,
                        confidence=97.0,
                    ),
                    OCRRegion(
                        text="Image citations stay stable.",
                        left=12,
                        top=58,
                        width=280,
                        height=24,
                        confidence=96.0,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="image-process-ready@example.com",
        username="image-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Image Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "whiteboard.png",
                _build_test_image_bytes(
                    text="PureLink image notes stay searchable",
                    image_format="PNG",
                ),
                "image/png",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 1
    metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    assert metadata["source_type"] == "image"
    assert metadata["source_locator"] == "image:ocr"
    assert metadata["ocr_provider"] == "fake_ocr"
    assert metadata["ocr_provider_version"] == "fake-v1"
    assert metadata["ocr_language"] == "eng"
    assert metadata["region_count"] == 2
    assert len(metadata["regions"]) == 2

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "image notes", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    image_result = retrieve_response.json()["results"][0]
    assert image_result["document_id"] == document_id
    assert image_result["document_name"] == "whiteboard.png"
    assert image_result["source_type"] == "image"
    _assert_api_source_locator(
        image_result["source_locator"],
        kind="image_region",
        source_locator_text="image:ocr",
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What stays stable in the image notes?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    image_citation = ask_response.json()["citations"][0]
    assert image_citation["document_name"] == "whiteboard.png"
    assert image_citation["source_type"] == "image"
    _assert_api_source_locator(
        image_citation["source_locator"],
        kind="image_region",
        source_locator_text="image:ocr",
    )


@pytest.mark.anyio
async def test_personal_image_document_auto_upgrades_to_indexed_after_process(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(
            result=OCRResult(
                text="PureLink screenshots can be indexed after OCR.",
                provider_name="fake_ocr",
                provider_version="fake-v2",
                language="eng",
                confidence=95.0,
                regions=(
                    OCRRegion(
                        text="PureLink screenshots can be indexed after OCR.",
                        left=20,
                        top=30,
                        width=420,
                        height=26,
                        confidence=95.0,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="image-indexed@example.com",
        username="image-indexed",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Image Indexed KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "product-shot.jpeg",
                _build_test_image_bytes(
                    text="PureLink screenshots can be indexed after OCR",
                    image_format="JPEG",
                ),
                "image/jpeg",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert [job.job_type for job in jobs] == [
        ProcessingJobType.DOCUMENT_PROCESS,
        ProcessingJobType.DOCUMENT_INDEX,
    ]
    assert [job.status for job in jobs] == [
        ProcessingJobStatus.SUCCEEDED,
        ProcessingJobStatus.SUCCEEDED,
    ]

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    indexed_chunk = index_payload["documents"][0]["chunks"][0]
    assert indexed_chunk["metadata"]["source_type"] == "image"
    assert indexed_chunk["metadata"]["source_locator"] == "image:ocr"
    assert indexed_chunk["metadata"]["ocr_provider"] == "fake_ocr"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "indexed after OCR", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["document_id"] == document_id
    assert retrieve_response.json()["results"][0]["source_type"] == "image"


@pytest.mark.anyio
async def test_personal_image_process_failure_marks_document_failed_for_ocr_error(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(error=OCRProviderError("Simulated OCR failure.")),
    )

    alice = await _register_and_login(
        document_client,
        email="image-ocr-failure@example.com",
        username="image-ocr-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Image OCR Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "broken-ocr.png",
                _build_test_image_bytes(
                    text="Broken OCR sample",
                    image_format="PNG",
                ),
                "image/png",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_document = db.get(Document, document_id)
        assert failed_document is not None
        assert failed_document.processing_status == DocumentProcessingStatus.FAILED
        assert failed_document.error_message == "Simulated OCR failure."
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )
        failed_job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.error_message == "Simulated OCR failure."


@pytest.mark.anyio
async def test_personal_image_index_failure_keeps_document_ready_and_retrieval_fallback(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_ocr_provider",
        lambda: FakeOCRProvider(
            result=OCRResult(
                text="Image fallback keeps OCR answers available.",
                provider_name="fake_ocr",
                provider_version="fake-v3",
                language="eng",
                confidence=94.0,
                regions=(
                    OCRRegion(
                        text="Image fallback keeps OCR answers available.",
                        left=18,
                        top=24,
                        width=360,
                        height=24,
                        confidence=94.0,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="image-index-failure@example.com",
        username="image-index-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Image Index Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "fallback-note.jpg",
                _build_test_image_bytes(
                    text="Image fallback keeps OCR answers available",
                    image_format="JPEG",
                ),
                "image/jpeg",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    def fail_embed_ready(*args, **kwargs):
        raise DocumentEmbeddingError("Simulated image indexing failure.")

    monkeypatch.setattr(
        document_indexing_service,
        "embed_ready_document_chunks",
        fail_embed_ready,
    )
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        failed_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_index_job is not None
        assert failed_index_job.status == ProcessingJobStatus.FAILED
        assert failed_index_job.error_message == "Simulated image indexing failure."

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "OCR answers available", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["document_id"] == document_id
    assert retrieve_response.json()["results"][0]["source_type"] == "image"

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What remains available after image indexing fails?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    image_citation = ask_response.json()["citations"][0]
    assert image_citation["document_id"] == document_id
    assert image_citation["source_type"] == "image"
    _assert_api_source_locator(
        image_citation["source_locator"],
        kind="image_region",
        source_locator_text="image:ocr",
    )


@pytest.mark.anyio
async def test_personal_audio_process_endpoint_marks_ready_creates_timestamped_chunks_and_supports_retrieval(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(
            result=ASRResult(
                full_text=(
                    "PureLink audio transcripts stay searchable. "
                    "Citation windows preserve the spoken time range."
                ),
                provider_name="fake_asr",
                provider_version="fake-v1",
                segments=(
                    ASRSegment(
                        text="PureLink audio transcripts stay searchable.",
                        start_time=0.0,
                        end_time=3.2,
                    ),
                    ASRSegment(
                        text="Citation windows preserve the spoken time range.",
                        start_time=3.2,
                        end_time=7.5,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="audio-process-ready@example.com",
        username="audio-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Audio Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "meeting.wav",
                _build_test_wav_bytes(duration_seconds=1.0),
                "audio/wav",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 2
    first_chunk_metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    second_chunk_metadata = json.loads(saved_chunks[1].metadata_json or "{}")
    assert first_chunk_metadata["source_type"] == "audio"
    assert first_chunk_metadata["start_time"] == 0.0
    assert first_chunk_metadata["end_time"] == 3.2
    assert first_chunk_metadata["source_locator"] == "time:0-3.2"
    assert first_chunk_metadata["asr_provider"] == "fake_asr"
    assert first_chunk_metadata["asr_provider_version"] == "fake-v1"
    assert second_chunk_metadata["source_type"] == "audio"
    assert second_chunk_metadata["start_time"] == 3.2
    assert second_chunk_metadata["end_time"] == 7.5
    assert second_chunk_metadata["source_locator"] == "time:3.2-7.5"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "spoken time range", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    audio_result = retrieve_response.json()["results"][0]
    assert audio_result["document_id"] == document_id
    assert audio_result["document_name"] == "meeting.wav"
    assert audio_result["source_type"] == "audio"
    assert audio_result["start_time"] == 3.2
    assert audio_result["end_time"] == 7.5
    _assert_api_source_locator(
        audio_result["source_locator"],
        kind="time_range",
        source_locator_text="time:3.2-7.5",
        start_time=3.2,
        end_time=7.5,
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What preserves the spoken time range?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    audio_citation = ask_response.json()["citations"][0]
    assert audio_citation["document_name"] == "meeting.wav"
    assert audio_citation["source_type"] == "audio"
    assert audio_citation["start_time"] == 3.2
    assert audio_citation["end_time"] == 7.5
    _assert_api_source_locator(
        audio_citation["source_locator"],
        kind="time_range",
        source_locator_text="time:3.2-7.5",
        start_time=3.2,
        end_time=7.5,
    )


@pytest.mark.anyio
async def test_personal_audio_document_auto_upgrades_to_indexed_after_process(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(
            result=ASRResult(
                full_text="Weekly audio digest keeps indexed answers available.",
                provider_name="fake_asr",
                provider_version="fake-v2",
                segments=(
                    ASRSegment(
                        text="Weekly audio digest keeps indexed answers available.",
                        start_time=4.0,
                        end_time=9.4,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="audio-indexed@example.com",
        username="audio-indexed",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Audio Indexed KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "weekly-digest.wav",
                _build_test_wav_bytes(duration_seconds=1.2),
                "audio/wav",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert [job.job_type for job in jobs] == [
        ProcessingJobType.DOCUMENT_PROCESS,
        ProcessingJobType.DOCUMENT_INDEX,
    ]
    assert [job.status for job in jobs] == [
        ProcessingJobStatus.SUCCEEDED,
        ProcessingJobStatus.SUCCEEDED,
    ]

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    indexed_chunk = index_payload["documents"][0]["chunks"][0]
    assert indexed_chunk["metadata"]["source_type"] == "audio"
    assert indexed_chunk["metadata"]["start_time"] == 4.0
    assert indexed_chunk["metadata"]["end_time"] == 9.4
    assert indexed_chunk["metadata"]["asr_provider"] == "fake_asr"
    assert indexed_chunk["metadata"]["source_locator"] == "time:4-9.4"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "indexed answers", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["document_id"] == document_id
    assert retrieve_response.json()["results"][0]["source_type"] == "audio"


@pytest.mark.anyio
async def test_personal_audio_process_failure_marks_document_failed_for_asr_error(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(error=ASRProviderError("Simulated ASR failure.")),
    )

    alice = await _register_and_login(
        document_client,
        email="audio-asr-failure@example.com",
        username="audio-asr-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Audio ASR Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "broken-audio.wav",
                _build_test_wav_bytes(duration_seconds=0.6),
                "audio/wav",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_document = db.get(Document, document_id)
        assert failed_document is not None
        assert failed_document.processing_status == DocumentProcessingStatus.FAILED
        assert failed_document.error_message == "Simulated ASR failure."
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )
        failed_job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.error_message == "Simulated ASR failure."


@pytest.mark.anyio
async def test_personal_audio_index_failure_keeps_document_ready_and_retrieval_fallback(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(
            result=ASRResult(
                full_text="Audio fallback keeps transcript answers available.",
                provider_name="fake_asr",
                provider_version="fake-v3",
                segments=(
                    ASRSegment(
                        text="Audio fallback keeps transcript answers available.",
                        start_time=12.0,
                        end_time=18.6,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="audio-index-failure@example.com",
        username="audio-index-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Audio Index Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "fallback-audio.wav",
                _build_test_wav_bytes(duration_seconds=1.4),
                "audio/wav",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    def fail_embed_ready(*args, **kwargs):
        raise DocumentEmbeddingError("Simulated audio indexing failure.")

    monkeypatch.setattr(
        document_indexing_service,
        "embed_ready_document_chunks",
        fail_embed_ready,
    )
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        failed_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_index_job is not None
        assert failed_index_job.status == ProcessingJobStatus.FAILED
        assert failed_index_job.error_message == "Simulated audio indexing failure."

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "transcript answers available", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    audio_result = retrieve_response.json()["results"][0]
    assert audio_result["document_id"] == document_id
    assert audio_result["source_type"] == "audio"
    assert audio_result["start_time"] == 12.0
    assert audio_result["end_time"] == 18.6

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What remains available after audio indexing fails?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    audio_citation = ask_response.json()["citations"][0]
    assert audio_citation["document_id"] == document_id
    assert audio_citation["source_type"] == "audio"
    assert audio_citation["start_time"] == 12.0
    assert audio_citation["end_time"] == 18.6
    _assert_api_source_locator(
        audio_citation["source_locator"],
        kind="time_range",
        source_locator_text="time:12-18.6",
        start_time=12.0,
        end_time=18.6,
    )


@pytest.mark.anyio
async def test_personal_video_process_endpoint_marks_ready_creates_timestamped_chunks_and_supports_retrieval(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_audio_from_video",
        lambda *, source_path, output_path: _write_extracted_video_audio(
            output_path=output_path,
            duration_seconds=1.1,
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(
            result=ASRResult(
                full_text=(
                    "PureLink video transcripts stay searchable. "
                    "Citation ranges preserve the clip timing."
                ),
                provider_name="fake_asr",
                provider_version="fake-v1",
                segments=(
                    ASRSegment(
                        text="PureLink video transcripts stay searchable.",
                        start_time=1.0,
                        end_time=4.4,
                    ),
                    ASRSegment(
                        text="Citation ranges preserve the clip timing.",
                        start_time=4.4,
                        end_time=8.1,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="video-process-ready@example.com",
        username="video-process-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Video Process Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "standup.mp4",
                _build_test_video_bytes(),
                "video/mp4",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )

    assert len(saved_chunks) == 2
    first_chunk_metadata = json.loads(saved_chunks[0].metadata_json or "{}")
    second_chunk_metadata = json.loads(saved_chunks[1].metadata_json or "{}")
    assert first_chunk_metadata["source_type"] == "video"
    assert first_chunk_metadata["start_time"] == 1.0
    assert first_chunk_metadata["end_time"] == 4.4
    assert first_chunk_metadata["source_locator"] == "time:1-4.4"
    assert first_chunk_metadata["asr_provider"] == "fake_asr"
    assert first_chunk_metadata["asr_provider_version"] == "fake-v1"
    assert second_chunk_metadata["source_type"] == "video"
    assert second_chunk_metadata["start_time"] == 4.4
    assert second_chunk_metadata["end_time"] == 8.1
    assert second_chunk_metadata["source_locator"] == "time:4.4-8.1"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "clip timing", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    video_result = retrieve_response.json()["results"][0]
    assert video_result["document_id"] == document_id
    assert video_result["document_name"] == "standup.mp4"
    assert video_result["source_type"] == "video"
    assert video_result["start_time"] == 4.4
    assert video_result["end_time"] == 8.1
    _assert_api_source_locator(
        video_result["source_locator"],
        kind="time_range",
        source_locator_text="time:4.4-8.1",
        start_time=4.4,
        end_time=8.1,
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What preserves the clip timing?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    video_citation = ask_response.json()["citations"][0]
    assert video_citation["document_name"] == "standup.mp4"
    assert video_citation["source_type"] == "video"
    assert video_citation["start_time"] == 4.4
    assert video_citation["end_time"] == 8.1
    _assert_api_source_locator(
        video_citation["source_locator"],
        kind="time_range",
        source_locator_text="time:4.4-8.1",
        start_time=4.4,
        end_time=8.1,
    )


@pytest.mark.anyio
async def test_personal_video_document_auto_upgrades_to_indexed_after_process(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_audio_from_video",
        lambda *, source_path, output_path: _write_extracted_video_audio(
            output_path=output_path,
            duration_seconds=1.3,
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(
            result=ASRResult(
                full_text="Weekly briefing video keeps indexed answers available.",
                provider_name="fake_asr",
                provider_version="fake-v2",
                segments=(
                    ASRSegment(
                        text="Weekly briefing video keeps indexed answers available.",
                        start_time=6.0,
                        end_time=12.8,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="video-indexed@example.com",
        username="video-indexed",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Video Indexed KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "briefing.mov",
                _build_test_video_bytes(),
                "video/quicktime",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert [job.job_type for job in jobs] == [
        ProcessingJobType.DOCUMENT_PROCESS,
        ProcessingJobType.DOCUMENT_INDEX,
    ]
    assert [job.status for job in jobs] == [
        ProcessingJobStatus.SUCCEEDED,
        ProcessingJobStatus.SUCCEEDED,
    ]

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    indexed_chunk = index_payload["documents"][0]["chunks"][0]
    assert indexed_chunk["metadata"]["source_type"] == "video"
    assert indexed_chunk["metadata"]["start_time"] == 6.0
    assert indexed_chunk["metadata"]["end_time"] == 12.8
    assert indexed_chunk["metadata"]["asr_provider"] == "fake_asr"
    assert indexed_chunk["metadata"]["source_locator"] == "time:6-12.8"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "indexed answers", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["document_id"] == document_id
    assert retrieve_response.json()["results"][0]["source_type"] == "video"


@pytest.mark.anyio
async def test_personal_video_process_failure_marks_document_failed_for_audio_extraction_error(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_audio_from_video",
        lambda *, source_path, output_path: (_ for _ in ()).throw(
            DocumentProcessingError("Simulated video audio extraction failure.")
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="video-audio-extract-failure@example.com",
        username="video-audio-extract-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Video Audio Extraction Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "broken-video.mp4",
                _build_test_video_bytes(),
                "video/mp4",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_document = db.get(Document, document_id)
        assert failed_document is not None
        assert failed_document.processing_status == DocumentProcessingStatus.FAILED
        assert failed_document.error_message == "Simulated video audio extraction failure."
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )
        failed_job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.error_message == "Simulated video audio extraction failure."


@pytest.mark.anyio
async def test_personal_video_process_failure_marks_document_failed_for_asr_error(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_audio_from_video",
        lambda *, source_path, output_path: _write_extracted_video_audio(
            output_path=output_path,
            duration_seconds=0.9,
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(error=ASRProviderError("Simulated video ASR failure.")),
    )

    alice = await _register_and_login(
        document_client,
        email="video-asr-failure@example.com",
        username="video-asr-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Video ASR Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "broken-asr-video.m4v",
                _build_test_video_bytes(),
                "video/x-m4v",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    with test_session_factory() as db:
        failed_document = db.get(Document, document_id)
        assert failed_document is not None
        assert failed_document.processing_status == DocumentProcessingStatus.FAILED
        assert failed_document.error_message == "Simulated video ASR failure."
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
        )
        failed_job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )

    assert saved_chunks == []
    assert failed_job is not None
    assert failed_job.status == ProcessingJobStatus.FAILED
    assert failed_job.error_message == "Simulated video ASR failure."


@pytest.mark.anyio
async def test_personal_video_index_failure_keeps_document_ready_and_retrieval_fallback(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setattr(
        "app.services.document_processing.extract_audio_from_video",
        lambda *, source_path, output_path: _write_extracted_video_audio(
            output_path=output_path,
            duration_seconds=1.5,
        ),
    )
    monkeypatch.setattr(
        "app.services.document_processing.resolve_asr_provider",
        lambda: FakeASRProvider(
            result=ASRResult(
                full_text="Video fallback keeps transcript answers available.",
                provider_name="fake_asr",
                provider_version="fake-v3",
                segments=(
                    ASRSegment(
                        text="Video fallback keeps transcript answers available.",
                        start_time=15.0,
                        end_time=22.4,
                    ),
                ),
            )
        ),
    )

    alice = await _register_and_login(
        document_client,
        email="video-index-failure@example.com",
        username="video-index-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Video Index Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "fallback-video.mp4",
                _build_test_video_bytes(),
                "video/mp4",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200

    processing_job_runner.run_all()

    def fail_embed_ready(*args, **kwargs):
        raise DocumentEmbeddingError("Simulated video indexing failure.")

    monkeypatch.setattr(
        document_indexing_service,
        "embed_ready_document_chunks",
        fail_embed_ready,
    )
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        failed_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_index_job is not None
        assert failed_index_job.status == ProcessingJobStatus.FAILED
        assert failed_index_job.error_message == "Simulated video indexing failure."

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "transcript answers available", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    video_result = retrieve_response.json()["results"][0]
    assert video_result["document_id"] == document_id
    assert video_result["source_type"] == "video"
    assert video_result["start_time"] == 15.0
    assert video_result["end_time"] == 22.4

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What remains available after video indexing fails?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    video_citation = ask_response.json()["citations"][0]
    assert video_citation["document_id"] == document_id
    assert video_citation["source_type"] == "video"
    assert video_citation["start_time"] == 15.0
    assert video_citation["end_time"] == 22.4
    _assert_api_source_locator(
        video_citation["source_locator"],
        kind="time_range",
        source_locator_text="time:15-22.4",
        start_time=15.0,
        end_time=22.4,
    )


@pytest.mark.anyio
async def test_personal_ready_document_auto_upgrades_to_indexed_after_process(
    document_client: AsyncClient,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="ready-to-indexed@example.com",
        username="ready-to-indexed",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Ready To Indexed KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "upgrade-manual.pdf",
                _build_minimal_pdf(text="Upgrade path keeps PDF citations available."),
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"
    assert process_response.json()["job_type"] == "document_process"
    assert len(processing_job_runner.submissions) == 1
    assert processing_job_runner.submissions[0]["job_type"] == "document_process"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        jobs_after_process = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
    assert [job.job_type for job in jobs_after_process] == [
        ProcessingJobType.DOCUMENT_PROCESS,
        ProcessingJobType.DOCUMENT_INDEX,
    ]
    assert jobs_after_process[0].status == ProcessingJobStatus.SUCCEEDED
    assert jobs_after_process[1].status == ProcessingJobStatus.QUEUED
    assert len(processing_job_runner.submissions) == 1
    assert processing_job_runner.submissions[0] == {
        "job_id": jobs_after_process[1].id,
        "document_id": document_id,
        "job_type": "document_index",
    }

    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        jobs_after_index = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
    assert jobs_after_index[1].status == ProcessingJobStatus.SUCCEEDED
    assert jobs_after_index[1].trigger_type == ProcessingJobTrigger.INDEX

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    assert index_file.exists()
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert index_payload["index_scheme"] == "json_vector_index_v1"
    assert index_payload["embedding_scheme"] == "hashed_bow_v1"
    assert index_payload["embedding_version"] == "hashed_bow_v1"
    assert index_payload["index_artifact_path"] == f"personal/knowledge_base_{knowledge_base_id}/index.json"
    indexed_documents = index_payload["documents"]
    assert indexed_documents
    indexed_chunk = indexed_documents[0]["chunks"][0]
    assert indexed_documents[0]["document_name"] == "upgrade-manual.pdf"
    assert indexed_chunk["metadata"]["source_type"] == "pdf"
    assert indexed_chunk["metadata"]["page_number"] == 1
    assert indexed_chunk["metadata"]["source_locator"] == "page:1"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "PDF citations", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    result = retrieve_response.json()["results"][0]
    assert result["document_id"] == document_id
    assert result["document_name"] == "upgrade-manual.pdf"
    assert result["source_type"] == "pdf"
    assert result["page_number"] == 1
    _assert_api_source_locator(
        result["source_locator"],
        kind="pdf_page",
        source_locator_text="page:1",
        page_number=1,
    )

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What stays available after upgrade?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    citation = ask_response.json()["citations"][0]
    assert citation["document_name"] == "upgrade-manual.pdf"
    assert citation["source_type"] == "pdf"
    assert citation["page_number"] == 1
    _assert_api_source_locator(
        citation["source_locator"],
        kind="pdf_page",
        source_locator_text="page:1",
        page_number=1,
    )


@pytest.mark.anyio
async def test_personal_new_upload_auto_rebuilds_stale_knowledge_base_index(
    document_client: AsyncClient,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="stale-kb-index@example.com",
        username="stale-kb-index",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Stale KB Index",
    )

    first_upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "baseline.txt",
                b"Baseline document keeps the knowledge base indexed.",
                "text/plain",
            )
        },
    )
    assert first_upload_response.status_code == 201
    first_document_id = first_upload_response.json()["id"]

    first_process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{first_document_id}/process",
        headers=alice_headers,
    )
    assert first_process_response.status_code == 200

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    assert index_file.exists()
    index_file.write_text(
        json.dumps(
            {
                "embedding_provider": "fastembed",
                "embedding_model": "BAAI/bge-small-zh-v1.5",
                "embedding_dimension": 384,
                "embedding_normalize": True,
                "documents": [
                    {
                        "document_id": first_document_id,
                        "document_name": "baseline.txt",
                        "embedding_provider": "fastembed",
                        "embedding_model": "BAAI/bge-small-zh-v1.5",
                        "embedding_dimension": 384,
                        "embedding_normalize": True,
                        "chunks": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    second_upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "fresh.txt",
                b"Fresh upload should trigger a knowledge base reindex.",
                "text/plain",
            )
        },
    )
    assert second_upload_response.status_code == 201
    second_document_id = second_upload_response.json()["id"]

    second_process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{second_document_id}/process",
        headers=alice_headers,
    )
    assert second_process_response.status_code == 200

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        first_document = db.get(Document, first_document_id)
        second_document = db.get(Document, second_document_id)
        assert first_document is not None
        assert second_document is not None
        assert first_document.processing_status == DocumentProcessingStatus.INDEXED
        assert second_document.processing_status == DocumentProcessingStatus.INDEXED
        second_document_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == second_document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )

    assert [job.status for job in second_document_jobs] == [
        ProcessingJobStatus.SUCCEEDED,
        ProcessingJobStatus.SUCCEEDED,
    ]

    rebuilt_payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert rebuilt_payload["embedding_provider"] == "local_hashed_bow"
    assert {item["document_id"] for item in rebuilt_payload["documents"]} == {
        first_document_id,
        second_document_id,
    }


@pytest.mark.anyio
async def test_personal_index_failure_keeps_document_ready_and_manual_embed_can_rebuild(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="index-failure-ready@example.com",
        username="index-failure-ready",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Index Failure Ready KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "index-failure.txt",
                b"PureLink ready fallback survives indexing failure.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    processing_job_runner.run_all()

    original_embed_ready = document_indexing_service.embed_ready_document_chunks

    def fail_embed_ready(*args, **kwargs):
        raise DocumentEmbeddingError("Simulated indexing failure.")

    monkeypatch.setattr(
        document_indexing_service,
        "embed_ready_document_chunks",
        fail_embed_ready,
    )
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        failed_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_index_job is not None
        assert failed_index_job.status == ProcessingJobStatus.FAILED
        assert failed_index_job.error_message == "Simulated indexing failure."

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "ready fallback", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["results"] == []

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What survives indexing failure?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    assert ask_response.json()["citations"] == []
    assert "没有找到足够可靠的依据" in ask_response.json()["answer"]

    monkeypatch.setattr(
        document_indexing_service,
        "embed_ready_document_chunks",
        original_embed_ready,
    )
    retry_body = await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
        processing_job_runner=processing_job_runner,
    )
    assert retry_body["document_status"] == "ready"

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED
        index_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.document_id == document_id,
                    ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
                )
                .order_by(ProcessingJob.id.asc())
            )
        )
    assert [job.status for job in index_jobs] == [
        ProcessingJobStatus.FAILED,
        ProcessingJobStatus.SUCCEEDED,
    ]


@pytest.mark.anyio
async def test_personal_document_indexes_with_external_embedding_provider_and_can_rebuild(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_API_BASE", "https://embedding.example/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "semantic-v1")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "4")
    get_settings.cache_clear()

    embedding_calls: list[dict[str, object]] = []

    class FakeEmbeddingResponse:
        def __init__(self, inputs: list[str]) -> None:
            self.inputs = inputs

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {"index": index, "embedding": _fake_semantic_vector(text)}
                    for index, text in enumerate(self.inputs)
                ]
            }

    def fake_embedding_post(url, *, headers, json, timeout):
        inputs = json["input"]
        if isinstance(inputs, str):
            inputs = [inputs]
        embedding_calls.append(
            {
                "url": url,
                "model": json["model"],
                "dimensions": json.get("dimensions"),
                "count": len(inputs),
                "authorization": headers["Authorization"],
                "timeout": timeout,
            }
        )
        return FakeEmbeddingResponse(list(inputs))

    monkeypatch.setattr("app.services.embedding_provider.httpx.post", fake_embedding_post)

    alice = await _register_and_login(
        document_client,
        email="external-embedding-success@example.com",
        username="external-embedding-success",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="External Embedding KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "external-semantic.txt",
                b"Semantic external embedding marker belongs to this indexed document.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_document = db.get(Document, document_id)
        assert indexed_document is not None
        assert indexed_document.processing_status == DocumentProcessingStatus.INDEXED

    index_file = tmp_path / "vector_store" / "personal" / f"knowledge_base_{knowledge_base_id}" / "index.json"
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert index_payload["embedding_scheme"] == "openai_compatible_embedding_v1"
    assert index_payload["embedding_provider"] == "openai_compatible"
    assert index_payload["embedding_model"] == "semantic-v1"
    assert index_payload["embedding_version"] == "semantic-v1"
    assert index_payload["embedding_dimension"] == 4
    assert index_payload["documents"][0]["embedding_model"] == "semantic-v1"
    assert embedding_calls[0]["url"] == "https://embedding.example/v1/embeddings"
    assert embedding_calls[0]["authorization"] == "Bearer test-embedding-key"

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "semantic external marker", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["results"]
    assert retrieve_body["results"][0]["document_id"] == document_id

    monkeypatch.setenv("EMBEDDING_MODEL", "semantic-v2")
    get_settings.cache_clear()
    rebuild_body = await _submit_manual_index_job(
        document_client,
        path=f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
        processing_job_runner=processing_job_runner,
    )
    assert rebuild_body["document_status"] == "indexed"

    rebuilt_payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert rebuilt_payload["embedding_model"] == "semantic-v2"
    assert rebuilt_payload["embedding_version"] == "semantic-v2"
    assert rebuilt_payload["documents"][0]["embedding_model"] == "semantic-v2"
    assert any(call["model"] == "semantic-v2" for call in embedding_calls)
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_external_embedding_failure_keeps_document_ready_and_retrieval_fallback(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_API_BASE", "https://embedding.example/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "semantic-v1")
    get_settings.cache_clear()

    def fail_embedding_post(*args, **kwargs):
        raise httpx.ConnectError("embedding provider unavailable")

    monkeypatch.setattr("app.services.embedding_provider.httpx.post", fail_embedding_post)

    alice = await _register_and_login(
        document_client,
        email="external-embedding-failure@example.com",
        username="external-embedding-failure",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="External Embedding Failure KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "external-failure.txt",
                b"External provider failure still leaves lexical ready fallback available.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    processing_job_runner.run_all()
    processing_job_runner.run_all()

    with test_session_factory() as db:
        ready_document = db.get(Document, document_id)
        assert ready_document is not None
        assert ready_document.processing_status == DocumentProcessingStatus.READY
        failed_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_index_job is not None
        assert failed_index_job.status == ProcessingJobStatus.FAILED
        assert "Embedding request failed" in (failed_index_job.error_message or "")

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "lexical ready fallback", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"] == []

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What remains available?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    assert ask_response.json()["citations"] == []
    assert "没有找到足够可靠的依据" in ask_response.json()["answer"]
    get_settings.cache_clear()


def _fake_semantic_vector(text: str) -> list[float]:
    lowered = text.lower()
    if "semantic" in lowered or "external" in lowered:
        return [1.0, 0.0, 0.0, 0.0]
    if "fallback" in lowered:
        return [0.0, 1.0, 0.0, 0.0]
    return [0.0, 0.0, 1.0, 0.0]


@pytest.mark.anyio
async def test_personal_markdown_process_failure_marks_document_failed_for_empty_text(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="md-process-empty@example.com",
        username="md-process-empty",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Markdown Process Empty KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("empty.md", b"\n   \n", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.FAILED
        assert saved_document.error_message == "Document does not contain valid text content."


@pytest.mark.anyio
async def test_personal_pdf_process_failure_marks_document_failed_for_invalid_pdf(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="pdf-process-invalid@example.com",
        username="pdf-process-invalid",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="PDF Process Invalid KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.FAILED
        assert saved_document.error_message == "Document is not a valid PDF file."


@pytest.mark.anyio
async def test_personal_docx_process_failure_marks_document_failed_for_invalid_docx(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="docx-process-invalid@example.com",
        username="docx-process-invalid",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="DOCX Process Invalid KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "broken.docx",
                b"not a docx archive",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    process_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/process",
        headers=alice_headers,
    )
    assert process_response.status_code == 200
    assert process_response.json()["job_status"] == "queued"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        saved_document = db.get(Document, document_id)
        assert saved_document is not None
        assert saved_document.processing_status == DocumentProcessingStatus.FAILED
        assert saved_document.error_message == "Document is not a valid DOCX file."


@pytest.mark.anyio
async def test_personal_document_reindex_alias_creates_index_job(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="personal-reindex-alias@example.com",
        username="personal-reindex-alias",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Reindex Alias KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={
            "file": (
                "reindex-alias.txt",
                b"PureLink reindex alias keeps indexing on the async path.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    reindex_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/reindex",
        headers=alice_headers,
    )
    assert reindex_response.status_code == 200
    reindex_body = reindex_response.json()
    assert reindex_body["job_type"] == "document_index"
    assert reindex_body["job_status"] == "queued"
    assert reindex_body["trigger_type"] == "index"

    processing_job_runner.run_all()

    with test_session_factory() as db:
        index_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.document_id == document_id,
                    ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
                )
                .order_by(ProcessingJob.id.asc())
            )
        )
        assert len(index_jobs) == 2
        assert [job.status for job in index_jobs] == [
            ProcessingJobStatus.SUCCEEDED,
            ProcessingJobStatus.SUCCEEDED,
        ]


@pytest.mark.anyio
async def test_personal_knowledge_base_reindex_clears_old_index_and_queues_document_index_jobs(
    document_client: AsyncClient,
    tmp_path: Path,
    test_session_factory: sessionmaker,
    processing_job_runner: CapturedProcessingJobRunner,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="personal-kb-reindex@example.com",
        username="personal-kb-reindex",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal KB Reindex",
    )

    uploaded_document_ids: list[int] = []
    for filename, content in (
        ("first.txt", b"First knowledge base document for reindex."),
        ("second.txt", b"Second knowledge base document for reindex."),
    ):
        upload_response = await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
            headers=alice_headers,
            files={"file": (filename, content, "text/plain")},
        )
        assert upload_response.status_code == 201
        uploaded_document_ids.append(upload_response.json()["id"])

    processing_job_runner.run_all()
    processing_job_runner.run_all()

    index_file = (
        tmp_path
        / "vector_store"
        / "personal"
        / f"knowledge_base_{knowledge_base_id}"
        / "index.json"
    )
    assert index_file.exists()

    reindex_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/reindex",
        headers=alice_headers,
    )
    assert reindex_response.status_code == 200
    reindex_body = reindex_response.json()
    assert sorted(reindex_body["queued_document_ids"]) == sorted(uploaded_document_ids)
    assert reindex_body["skipped_document_ids"] == []
    assert len(reindex_body["queued_jobs"]) == 2
    assert all(job["job_type"] == "document_index" for job in reindex_body["queued_jobs"])
    assert index_file.exists() is False

    processing_job_runner.run_all()

    with test_session_factory() as db:
        indexed_documents = [
            db.get(Document, document_id) for document_id in uploaded_document_ids
        ]
        assert all(document is not None for document in indexed_documents)
        assert all(
            document.processing_status == DocumentProcessingStatus.INDEXED
            for document in indexed_documents
            if document is not None
        )

    assert index_file.exists()
