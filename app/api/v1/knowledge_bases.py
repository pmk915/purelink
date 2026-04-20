from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.api.deps import CurrentUser, DBSession
from app.core.config import BASE_DIR, get_settings
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    DocumentTaskType,
    KnowledgeBaseScope,
)
from app.schemas.document import (
    DocumentChunkRead,
    DocumentEmbedRead,
    DocumentParseRead,
    DocumentRead,
    RetrievalQueryRequest,
    RetrievalResponse,
    RetrievedChunkRead,
)
from app.schemas.qa import QuestionAnswerRequest, QuestionAnswerResponse
from app.schemas.document_task import DocumentTaskRead
from app.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseRead,
    KnowledgeBaseUpdateRequest,
)
from app.services.document import (
    create_document,
    get_document_for_knowledge_base,
    list_documents_for_knowledge_base,
    resolve_upload_root,
    store_document_file,
    update_document_processing_status,
)
from app.services.document_chunker import (
    DocumentChunkError,
    chunk_document_from_parsed_result,
    resolve_chunks_root,
)
from app.services.document_embedding import (
    DocumentEmbeddingError,
    embed_document_chunks,
    resolve_vector_store_root,
)
from app.services.document_parser import (
    DocumentParseError,
    parse_document_to_local_result,
    resolve_parsed_root,
)
from app.services.conversation import (
    ConversationKnowledgeBaseMismatchError,
    ConversationNotFoundError,
    get_or_create_conversation_for_question,
    persist_question_answer_exchange,
)
from app.services.qa import AnswerGenerationError, answer_question
from app.services.retrieval import retrieve_chunks_for_documents
from app.services.document_task import (
    ActiveDocumentTaskExistsError,
    DocumentTaskEligibilityError,
    create_document_task_for_document,
)
from app.services.knowledge_base import (
    UNSET,
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base_for_user,
    list_knowledge_bases_for_user,
    update_knowledge_base,
)


router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _get_owned_knowledge_base_or_404(
    db: DBSession,
    *,
    knowledge_base_id: int,
    user_id: int,
):
    knowledge_base = get_knowledge_base_for_user(
        db,
        owner_id=user_id,
        knowledge_base_id=knowledge_base_id,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base_endpoint(
    payload: KnowledgeBaseCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    knowledge_base = create_knowledge_base(
        db,
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.get("", response_model=list[KnowledgeBaseRead])
async def list_knowledge_bases_endpoint(
    db: DBSession,
    current_user: CurrentUser,
) -> list[KnowledgeBaseRead]:
    knowledge_bases = list_knowledge_bases_for_user(db, owner_id=current_user.id)
    return [KnowledgeBaseRead.model_validate(item) for item in knowledge_bases]


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def get_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base_endpoint(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    update_data = payload.model_dump(exclude_unset=True)
    updated = update_knowledge_base(
        db,
        knowledge_base=knowledge_base,
        name=update_data.get("name"),
        description=update_data.get("description", UNSET),
    )
    return KnowledgeBaseRead.model_validate(updated)


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    delete_knowledge_base(db, knowledge_base=knowledge_base)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_to_personal_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> DocumentRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    internal_filename, storage_path = store_document_file(
        upload_root=upload_root,
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=knowledge_base.id,
        original_filename=file.filename,
        content=content,
    )
    document = create_document(
        db,
        knowledge_base_id=knowledge_base.id,
        owner_id=current_user.id,
        submitted_by=current_user.id,
        filename=internal_filename,
        original_filename=file.filename,
        file_type=file.content_type or "application/octet-stream",
        file_size=len(content),
        storage_path=storage_path,
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    return DocumentRead.model_validate(document)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
async def list_personal_knowledge_base_documents_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[DocumentRead]:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )
    return [DocumentRead.model_validate(item) for item in documents]


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse",
    response_model=DocumentParseRead,
)
async def parse_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentParseRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for parsing.",
        )

    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)

    try:
        parsed_result = parse_document_to_local_result(
            document=document,
            upload_root=upload_root,
            parsed_root=parsed_root,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except DocumentParseError as exc:
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    update_document_processing_status(
        db,
        document=document,
        processing_status=DocumentProcessingStatus.PARSED,
    )
    return DocumentParseRead(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        processing_status=document.processing_status,
        parsed_path=parsed_result.parsed_path,
        parser=parsed_result.parser,
        extracted_char_count=parsed_result.extracted_char_count,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/chunk",
    response_model=DocumentChunkRead,
)
async def chunk_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentChunkRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for chunking.",
        )
    if document.processing_status != DocumentProcessingStatus.PARSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document must be parsed before chunking.",
        )

    settings = get_settings()
    parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)
    chunks_root = resolve_chunks_root(settings.chunks_dir, base_dir=BASE_DIR)
    try:
        chunked_result = chunk_document_from_parsed_result(
            document=document,
            parsed_root=parsed_root,
            chunks_root=chunks_root,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except DocumentChunkError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return DocumentChunkRead(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        processing_status=document.processing_status,
        chunked_path=chunked_result.chunked_path,
        source_parsed_path=chunked_result.source_parsed_path,
        chunk_count=chunked_result.chunk_count,
        chunk_size=chunked_result.chunk_size,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/embed",
    response_model=DocumentEmbedRead,
)
async def embed_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentEmbedRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for embedding.",
        )
    if document.processing_status not in {
        DocumentProcessingStatus.PARSED,
        DocumentProcessingStatus.INDEXED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document must be chunked and parsed before embedding.",
        )

    settings = get_settings()
    chunks_root = resolve_chunks_root(settings.chunks_dir, base_dir=BASE_DIR)
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    try:
        embedded_result = embed_document_chunks(
            document=document,
            chunks_root=chunks_root,
            vector_root=vector_root,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except DocumentEmbeddingError as exc:
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    update_document_processing_status(
        db,
        document=document,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    return DocumentEmbedRead(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        processing_status=document.processing_status,
        index_path=embedded_result.index_path,
        embedded_chunk_count=embedded_result.embedded_chunk_count,
        embedding_dimension=embedded_result.embedding_dimension,
    )


@router.post(
    "/{knowledge_base_id}/retrieve",
    response_model=RetrievalResponse,
)
async def retrieve_personal_knowledge_base_chunks_endpoint(
    knowledge_base_id: int,
    payload: RetrievalQueryRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> RetrievalResponse:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )

    settings = get_settings()
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    try:
        results = retrieve_chunks_for_documents(
            documents=documents,
            vector_root=vector_root,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query=payload.query,
            top_k=payload.top_k,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )
    except DocumentEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return RetrievalResponse(
        query=payload.query,
        top_k=payload.top_k,
        results=[
            RetrievedChunkRead(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                knowledge_base_id=item.knowledge_base_id,
                scope=item.scope,
                team_id=item.team_id,
                text=item.text,
                score=item.score,
            )
            for item in results
        ],
    )


@router.post(
    "/{knowledge_base_id}/ask",
    response_model=QuestionAnswerResponse,
)
async def ask_personal_knowledge_base_endpoint(
    knowledge_base_id: int,
    payload: QuestionAnswerRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> QuestionAnswerResponse:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )

    settings = get_settings()
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    try:
        retrieved_chunks = retrieve_chunks_for_documents(
            documents=documents,
            vector_root=vector_root,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query=payload.question,
            top_k=payload.top_k,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )
    except DocumentEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        qa_result = answer_question(
            question=payload.question,
            retrieved_chunks=retrieved_chunks,
        )
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        conversation = get_or_create_conversation_for_question(
            db,
            user_id=current_user.id,
            knowledge_base_id=knowledge_base.id,
            question=payload.question,
            conversation_id=payload.conversation_id,
        )
        persist_question_answer_exchange(
            db,
            conversation=conversation,
            question=payload.question,
            answer=qa_result.answer,
            citations=qa_result.citations,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConversationKnowledgeBaseMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return QuestionAnswerResponse(
        conversation_id=conversation.id,
        answer=qa_result.answer,
        citations=qa_result.citations,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_document_parse_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.PARSE,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_document_chunk_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.CHUNK,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/embed-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_document_embed_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.EMBED,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/index-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_document_index_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.INDEX,
            scope=KnowledgeBaseScope.PERSONAL,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)
