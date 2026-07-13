from __future__ import annotations

import logging

from app.core.config import get_settings
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope, RetrievalFilteredReason
from app.services.indexing.index_metadata_service import (
    LEGACY_UNKNOWN_INDEX_REASON,
    MODEL_MISMATCH_REASON,
    PROVIDER_MISMATCH_REASON,
    STATUS_NOT_INDEXED_REASON,
    DIMENSION_MISMATCH_REASON,
    VectorIndexCompatibilityDecision,
    evaluate_documents_vector_index_compatibility,
    get_vector_index_identity_from_settings,
)
from app.services.embedding_provider import EmbeddingProviderError
from app.services.knowledge_graph.graph_retriever import (
    merge_graph_and_vector_chunks,
    retrieve_graph_chunks,
)
from app.services.retrieval import chunk_retriever
from app.services.retrieval.citation_builder import (
    build_evidences,
    citation_readiness,
    summarize_citation_readiness,
)
from app.services.retrieval.context_builder import build_context
from app.services.retrieval.hybrid_text_retriever import retrieve_hybrid_text_chunks
from app.services.retrieval.overview_retriever_adapter import retrieve_overview_chunks
from app.services.retrieval.query_router import CONFIDENCE_MANUAL, QueryRouteDecision, route_query
from app.services.retrieval.rerank_service import (
    align_chunks_to_evidences,
    rerank_evidences,
    should_expand_initial_recall,
)
from app.services.retrieval.retrieval_router import resolve_mode
from app.services.retrieval import trace_service
from app.services.retrieval.trace_types import RetrievalTraceCandidate
from app.services.retrieval.types import RetrievalMode, RetrievalRequest, RetrievalResult
from app.services.query_analysis import (
    EVIDENCE_QUERY_ATTRIBUTE,
    TargetDocumentDecision,
    analyze_evidence_query,
    resolve_target_documents,
)


logger = logging.getLogger("purelink.retrieval")


async def retrieve(request: RetrievalRequest) -> RetrievalResult:
    active_settings = request.settings or get_settings()
    requested_mode = request.mode
    routing_query_source = "evidence_query" if request.evidence_query else "query"
    route_decision = _select_retrieval_mode(request)
    resolved_mode = route_decision.selected_mode
    effective_mode = resolved_mode
    fallback_mode: RetrievalMode | None = None
    fallback_reason: str | None = None
    final_top_k = request.top_k
    expand_for_reranker = should_expand_initial_recall(active_settings)
    initial_top_k = (
        max(final_top_k, active_settings.reranker_top_n)
        if expand_for_reranker
        and resolved_mode in {RetrievalMode.CHUNK_ONLY, RetrievalMode.GRAPH_VECTOR_MIX, RetrievalMode.HYBRID_TEXT}
        else final_top_k
    )

    _validate_internal_context(request, mode=effective_mode)
    scope = _coerce_scope(request.scope)
    required_review_status = _coerce_review_status(request.required_review_status)
    trace_id = _safe_start_trace(
        request=request,
        settings=active_settings,
        mode=resolved_mode,
    )
    documents, index_decisions = _filter_compatible_documents(
        request=request,
        settings=active_settings,
    )
    overview_target_decision: TargetDocumentDecision | None = None
    overview_metadata: dict[str, object] = {}

    try:
        if resolved_mode == RetrievalMode.OVERVIEW:
            overview_target_decision = resolve_target_documents(
                request.evidence_query or request.query,
                request.documents,
            )
            overview_metadata = _build_overview_metadata(overview_target_decision)
            raw_chunks = retrieve_overview_chunks(
                db=request.db,
                documents=request.documents,
                knowledge_base_id=request.knowledge_base_id,
                scope=scope,
                required_review_status=required_review_status,
                team_id=request.team_id,
                settings=active_settings,
                query=request.evidence_query or request.query,
                target_document_ids=(
                    overview_target_decision.target_document_ids
                    if overview_target_decision.target_requested
                    else None
                ),
                overview_scope=str(overview_metadata["overview_scope"]),
                target_document_requested=overview_target_decision.target_requested,
            )
            context_chunks = raw_chunks
        else:
            hybrid_metadata = None
            if effective_mode == RetrievalMode.HYBRID_TEXT:
                raw_chunks, hybrid_metadata = retrieve_hybrid_text_chunks(
                    db=request.db,
                    documents=documents,
                    keyword_documents=request.documents,
                    vector_root=request.vector_root,
                    scope=scope,
                    knowledge_base_id=request.knowledge_base_id,
                    query=request.query,
                    top_k=initial_top_k,
                    required_review_status=required_review_status,
                    team_id=request.team_id,
                )
                fallback_mode, fallback_reason = _hybrid_fallback_metadata(
                    hybrid_metadata=hybrid_metadata,
                    raw_chunks=raw_chunks,
                )
                if fallback_mode is not None:
                    effective_mode = fallback_mode
            else:
                raw_chunks = chunk_retriever.retrieve_chunks_for_documents(
                    db=request.db,
                    documents=documents,
                    vector_root=request.vector_root,
                    scope=scope,
                    knowledge_base_id=request.knowledge_base_id,
                    query=request.query,
                    top_k=initial_top_k,
                    required_review_status=required_review_status,
                    team_id=request.team_id,
                )
            graph_chunks = []
            if effective_mode == RetrievalMode.GRAPH_VECTOR_MIX:
                try:
                    graph_chunks = retrieve_graph_chunks(
                        db=request.db,
                        documents=documents,
                        knowledge_base_id=request.knowledge_base_id,
                        query=request.query,
                        scope=scope.value,
                        team_id=request.team_id,
                        limit=initial_top_k,
                    )
                except Exception:
                    logger.warning("graph retrieval failed; falling back to chunk_only", exc_info=True)
                    graph_chunks = []
                    effective_mode = RetrievalMode.CHUNK_ONLY
                    fallback_mode = RetrievalMode.CHUNK_ONLY
                    fallback_reason = "graph_retrieval_failed"
                else:
                    graph_fallback_reason = _graph_fallback_reason(
                        graph_chunks=graph_chunks,
                        min_score=active_settings.retrieval_min_score,
                    )
                    if graph_fallback_reason:
                        effective_mode = RetrievalMode.CHUNK_ONLY
                        fallback_mode = RetrievalMode.CHUNK_ONLY
                        fallback_reason = graph_fallback_reason
                    else:
                        raw_chunks = merge_graph_and_vector_chunks(
                            vector_chunks=raw_chunks,
                            graph_chunks=graph_chunks,
                            top_k=initial_top_k,
                        )
            context_chunks = (
                raw_chunks
                if expand_for_reranker
                else _select_context_chunks(
                    raw_chunks,
                    question=request.evidence_query or request.query,
                )
            )
            graph_chunk_keys = {
                (item.document_id, str(item.chunk_id))
                for item in graph_chunks
            }

        evidence_units = []
        evidence_selection_metadata: dict[str, object] = {}
        if request.include_citations:
            evidence_units, evidence_selection_metadata = _select_evidence_units(
                db=request.db,
                query=request.evidence_query or request.query,
                context_chunks=context_chunks,
                max_evidence_units=(
                    initial_top_k
                    if expand_for_reranker
                    else max(active_settings.max_citations, 8)
                ),
                use_query_evidence_profile=effective_mode != RetrievalMode.OVERVIEW,
            )

        evidence_source = evidence_units if request.include_citations else context_chunks
        candidate_evidences = _annotate_chunk_score_evidences(
            _annotate_graph_evidences(
                build_evidences(evidence_source),
                graph_chunk_keys=locals().get("graph_chunk_keys", set()),
            ),
            chunks=raw_chunks,
            retrieval_mode=effective_mode,
        )
        evidences, used_reranker = await rerank_evidences(
            query=request.evidence_query or request.query,
            evidences=candidate_evidences,
            top_k=final_top_k,
            settings=active_settings,
        )
        if used_reranker:
            context_chunks = align_chunks_to_evidences(
                chunks=raw_chunks,
                evidences=evidences,
            ) or context_chunks[:final_top_k]
            evidence_units = _align_raw_items_to_evidences(
                items=evidence_units,
                evidences=evidences,
            )
        else:
            evidences = candidate_evidences
            evidence_units = _align_raw_items_to_evidences(
                items=evidence_units,
                evidences=evidences,
            )

        _safe_record_trace_items(
            request=request,
            trace_id=trace_id,
            candidate_evidences=candidate_evidences,
            final_evidences=evidences,
            used_reranker=used_reranker,
            index_decisions=index_decisions,
        )
        _safe_finish_trace(
            request=request,
            trace_id=trace_id,
            initial_candidate_count=len(raw_chunks),
            final_evidence_count=len(evidences),
            used_reranker=used_reranker,
            metadata={
                "mode": effective_mode.value,
                **_build_router_metadata(
                    requested_mode=requested_mode,
                    selected_mode=resolved_mode,
                    effective_mode=effective_mode,
                    router_reason=route_decision.reason,
                    router_confidence=route_decision.confidence,
                    fallback_mode=fallback_mode,
                    fallback_reason=fallback_reason,
                    routing_query_source=routing_query_source,
                ),
                **overview_metadata,
                **evidence_selection_metadata,
                "context_chunk_count": len(context_chunks),
                "evidence_unit_count": len(evidence_units),
                "graph_candidate_count": len(locals().get("graph_chunks", [])),
                "graph_used": bool(locals().get("graph_chunks", [])),
                "keyword_candidate_count": getattr(locals().get("hybrid_metadata"), "keyword_candidate_count", 0),
                "hybrid_fallback_reason": getattr(locals().get("hybrid_metadata"), "fallback_reason", None),
                **summarize_citation_readiness(evidences),
            },
        )

        context_text = build_context(evidences)
        retrieved_chunks = context_chunks if used_reranker else raw_chunks

        logger.info(
            "retrieval completed knowledge_base_id=%s user_id=%s routed_mode=%s effective_mode=%s initial_top_k=%s final_top_k=%s raw_chunk_count=%s context_chunk_count=%s evidence_count=%s used_reranker=%s trace_id=%s fallback_reason=%s",
            request.knowledge_base_id,
            request.user_id,
            resolved_mode.value,
            effective_mode.value,
            initial_top_k,
            final_top_k,
            len(raw_chunks),
            len(context_chunks),
            len(evidences),
            used_reranker,
            trace_id,
            fallback_reason,
        )
        return RetrievalResult(
            query=request.query,
            mode=effective_mode,
            requested_mode=requested_mode,
            selected_mode=resolved_mode,
            router_reason=route_decision.reason,
            router_confidence=route_decision.confidence,
            effective_mode=effective_mode,
            fallback_mode=fallback_mode,
            fallback_reason=fallback_reason,
            evidences=evidences,
            context_text=context_text,
            used_reranker=used_reranker,
            trace_id=trace_id,
            metadata={
                **_build_router_metadata(
                    requested_mode=requested_mode,
                    selected_mode=resolved_mode,
                    effective_mode=effective_mode,
                    router_reason=route_decision.reason,
                    router_confidence=route_decision.confidence,
                    fallback_mode=fallback_mode,
                    fallback_reason=fallback_reason,
                    routing_query_source=routing_query_source,
                ),
                **overview_metadata,
                **evidence_selection_metadata,
                "retrieved_chunks": retrieved_chunks,
                "initial_chunks": raw_chunks,
                "context_chunks": context_chunks,
                "evidence_units": evidence_units,
                "graph_chunks": locals().get("graph_chunks", []),
                "keyword_candidate_count": getattr(locals().get("hybrid_metadata"), "keyword_candidate_count", 0),
                "hybrid_fallback_reason": getattr(locals().get("hybrid_metadata"), "fallback_reason", None),
            },
        )
    except Exception as exc:
        _safe_finish_trace(
            request=request,
            trace_id=trace_id,
            initial_candidate_count=0,
            final_evidence_count=0,
            used_reranker=False,
            metadata={
                **_build_router_metadata(
                    requested_mode=requested_mode,
                    selected_mode=resolved_mode,
                    effective_mode=effective_mode,
                    router_reason=route_decision.reason,
                    router_confidence=route_decision.confidence,
                    fallback_mode=fallback_mode,
                    fallback_reason=fallback_reason,
                    routing_query_source=routing_query_source,
                ),
                **overview_metadata,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        raise


def _select_retrieval_mode(request: RetrievalRequest) -> QueryRouteDecision:
    if request.mode == RetrievalMode.AUTO:
        return route_query(request.evidence_query or request.query)
    return QueryRouteDecision(
        selected_mode=resolve_mode(request.mode),
        reason="manual mode specified",
        confidence=CONFIDENCE_MANUAL,
    )


def _build_router_metadata(
    *,
    requested_mode: RetrievalMode,
    selected_mode: RetrievalMode,
    effective_mode: RetrievalMode,
    router_reason: str | None,
    router_confidence: str | None,
    fallback_mode: RetrievalMode | None,
    fallback_reason: str | None,
    routing_query_source: str,
) -> dict[str, object]:
    return {
        "requested_mode": requested_mode.value,
        "selected_mode": selected_mode.value,
        "effective_mode": effective_mode.value,
        "router_reason": router_reason,
        "router_confidence": router_confidence,
        "router_type": "rule_based" if requested_mode == RetrievalMode.AUTO else None,
        "fallback_mode": fallback_mode.value if fallback_mode else None,
        "fallback_reason": fallback_reason,
        "routing_query_source": routing_query_source,
    }


def _build_overview_metadata(decision: TargetDocumentDecision) -> dict[str, object]:
    return {
        "overview_scope": (
            "document_targeted" if decision.target_requested else "knowledge_base"
        ),
        "target_document_requested": decision.target_requested,
        "target_document_ids": list(decision.target_document_ids),
        "target_document_terms": list(decision.matched_terms),
        "target_document_confidence": decision.confidence,
        "target_document_reason": decision.reason,
    }


def _graph_fallback_reason(*, graph_chunks, min_score: float) -> str | None:
    if not graph_chunks:
        return "graph_candidates_empty"
    threshold = max(0.0, float(min_score))
    if all(getattr(chunk, "score", 0.0) < threshold for chunk in graph_chunks):
        return "graph_candidates_below_threshold"
    return None


def _hybrid_fallback_metadata(*, hybrid_metadata, raw_chunks) -> tuple[RetrievalMode | None, str | None]:
    if hybrid_metadata is None:
        return None, None
    if getattr(hybrid_metadata, "keyword_failed", False):
        return RetrievalMode.CHUNK_ONLY, "keyword_retrieval_failed"
    if getattr(hybrid_metadata, "keyword_candidate_count", 0) <= 0:
        return RetrievalMode.CHUNK_ONLY, "keyword_candidates_empty"
    if raw_chunks and not any("keyword" in (getattr(chunk, "candidate_sources", ()) or ()) for chunk in raw_chunks):
        return RetrievalMode.CHUNK_ONLY, "hybrid_no_additional_signal"
    return None, None


def _validate_internal_context(request: RetrievalRequest, *, mode: RetrievalMode | None = None) -> None:
    if request.db is None:
        raise ValueError("RetrievalRequest.db is required for M1 retrieval.")
    if request.scope is None:
        raise ValueError("RetrievalRequest.scope is required for M1 retrieval.")
    if request.required_review_status is None:
        raise ValueError("RetrievalRequest.required_review_status is required for M1 retrieval.")
    resolved_mode = mode or resolve_mode(request.mode)
    if resolved_mode in {RetrievalMode.CHUNK_ONLY, RetrievalMode.GRAPH_VECTOR_MIX, RetrievalMode.HYBRID_TEXT} and request.vector_root is None:
        raise ValueError("RetrievalRequest.vector_root is required for chunk retrieval.")


def _safe_start_trace(
    *,
    request: RetrievalRequest,
    settings: object,
    mode: RetrievalMode,
) -> int | None:
    if not request.enable_trace:
        return None
    if request.db is None:
        return None

    embedding_provider, embedding_model = _get_embedding_trace_identity(settings)
    try:
        trace = trace_service.start_retrieval_trace(
            request.db,
            user_id=request.user_id,
            knowledge_base_id=request.knowledge_base_id,
            conversation_id=request.conversation_id,
            message_id=request.message_id,
            query=request.query,
            mode=mode.value,
            top_k=request.top_k,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            reranker_enabled=bool(getattr(settings, "reranker_enabled", False)),
            reranker_provider=getattr(settings, "reranker_provider", None),
            reranker_model=getattr(settings, "reranker_model", None) or None,
        )
    except Exception:
        logger.exception("failed to start retrieval trace")
        return None
    return trace.id


def _safe_finish_trace(
    *,
    request: RetrievalRequest,
    trace_id: int | None,
    initial_candidate_count: int,
    final_evidence_count: int,
    used_reranker: bool,
    metadata: dict[str, object] | None = None,
) -> None:
    if trace_id is None or request.db is None:
        return
    try:
        trace_service.finish_retrieval_trace(
            request.db,
            trace_id=trace_id,
            initial_candidate_count=initial_candidate_count,
            final_evidence_count=final_evidence_count,
            used_reranker=used_reranker,
            metadata=metadata,
        )
    except Exception:
        logger.exception("failed to finish retrieval trace trace_id=%s", trace_id)


def _safe_record_trace_items(
    *,
    request: RetrievalRequest,
    trace_id: int | None,
    candidate_evidences,
    final_evidences,
    used_reranker: bool,
    index_decisions: list[VectorIndexCompatibilityDecision],
) -> None:
    if trace_id is None or request.db is None:
        return
    try:
        candidates = _build_trace_candidates(
            candidate_evidences=candidate_evidences,
            final_evidences=final_evidences,
            used_reranker=used_reranker,
            index_decisions=index_decisions,
        )
        trace_service.record_retrieval_trace_items(
            request.db,
            trace_id=trace_id,
            candidates=candidates,
        )
    except Exception:
        logger.exception("failed to record retrieval trace items trace_id=%s", trace_id)


def _filter_compatible_documents(
    *,
    request: RetrievalRequest,
    settings: object,
) -> tuple[list[object], list[VectorIndexCompatibilityDecision]]:
    if request.db is None:
        return list(request.documents), []

    try:
        provider, model_name, model_dim, _ = get_vector_index_identity_from_settings(settings)
    except EmbeddingProviderError:
        logger.warning("index compatibility check skipped because embedding provider is unavailable")
        return list(request.documents), []
    decisions = evaluate_documents_vector_index_compatibility(
        request.db,
        documents=request.documents,
        current_provider=provider,
        current_model_name=model_name,
        current_model_dim=model_dim,
    )
    decision_by_document_id = {item.document_id: item for item in decisions}
    allowed = []
    for document in request.documents:
        decision = decision_by_document_id.get(document.id)
        if decision is None or decision.allowed:
            allowed.append(document)
            continue
        logger.info(
            "document vector index skipped document_id=%s knowledge_base_id=%s reason=%s",
            document.id,
            getattr(document, "knowledge_base_id", None),
            decision.reason,
        )
    return allowed, decisions


def _get_embedding_trace_identity(settings: object) -> tuple[str | None, str | None]:
    try:
        provider, model_name, _, _ = get_vector_index_identity_from_settings(settings)
    except EmbeddingProviderError:
        return None, None
    return provider, model_name


def _build_trace_candidates(
    *,
    candidate_evidences,
    final_evidences,
    used_reranker: bool,
    index_decisions: list[VectorIndexCompatibilityDecision],
) -> list[RetrievalTraceCandidate]:
    final_rank_by_key = {
        _evidence_trace_key(evidence): index
        for index, evidence in enumerate(final_evidences, start=1)
    }
    final_evidence_by_key = {
        _evidence_trace_key(evidence): evidence
        for evidence in final_evidences
    }

    candidates: list[RetrievalTraceCandidate] = []
    for index, evidence in enumerate(candidate_evidences, start=1):
        key = _evidence_trace_key(evidence)
        final_rank = final_rank_by_key.get(key)
        final_evidence = final_evidence_by_key.get(key, evidence)
        selected = final_rank is not None
        citation_ready, citation_readiness_reason = citation_readiness(evidence)
        candidates.append(
            RetrievalTraceCandidate(
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_db_id,
                citation_unit_id=evidence.citation_unit_id,
                document_name=evidence.document_name,
                source_locator=evidence.source_locator,
                candidate_text_preview=evidence.text,
                vector_score=evidence.vector_score or evidence.final_score,
                keyword_score=evidence.keyword_score,
                graph_score=evidence.graph_score,
                rerank_score=final_evidence.rerank_score,
                final_score=final_evidence.final_score,
                initial_rank=index,
                rerank_rank=final_rank if used_reranker and selected else None,
                final_rank=final_rank,
                selected_for_context=selected,
                filtered_reason=(
                    RetrievalFilteredReason.NOT_FILTERED
                    if selected
                    else RetrievalFilteredReason.NOT_SELECTED_AFTER_RERANK
                    if used_reranker
                    else RetrievalFilteredReason.UNKNOWN
                ),
                metadata={
                    "chunk_key": str(evidence.chunk_id),
                    "marker": evidence.metadata.get("marker"),
                    "candidate_sources": evidence.metadata.get("candidate_sources"),
                    "matched_terms": evidence.metadata.get("matched_terms"),
                    "retrieval_mode": evidence.metadata.get("retrieval_mode"),
                    "citation_ready": citation_ready,
                    "citation_readiness_reason": citation_readiness_reason,
                    "attribute_match": evidence.metadata.get("attribute_match"),
                    "identifier_match": evidence.metadata.get("identifier_match"),
                    "entity_match": evidence.metadata.get("entity_match"),
                    "direct_support": evidence.metadata.get("direct_support"),
                    "coverage_gain": evidence.metadata.get("coverage_gain"),
                    "rejection_reason": evidence.metadata.get("rejection_reason"),
                },
            )
        )

    seen_document_ids = {item.document_id for item in candidates if item.document_id is not None}
    for decision in index_decisions:
        if decision.allowed or decision.document_id in seen_document_ids:
            continue
        candidates.append(
            RetrievalTraceCandidate(
                document_id=decision.document_id,
                filtered_reason=_map_index_filter_reason(decision),
                index_status=decision.index_status,
                index_provider=decision.index_provider,
                index_model_name=decision.index_model_name,
                index_model_dim=decision.index_model_dim,
            )
        )
    return candidates


def _map_index_filter_reason(
    decision: VectorIndexCompatibilityDecision,
) -> RetrievalFilteredReason:
    if decision.reason == LEGACY_UNKNOWN_INDEX_REASON:
        return RetrievalFilteredReason.LEGACY_UNKNOWN_ALLOWED
    if decision.reason == STATUS_NOT_INDEXED_REASON:
        return RetrievalFilteredReason.STALE_INDEX if decision.index_status == "stale" else RetrievalFilteredReason.DOCUMENT_NOT_READY
    if decision.reason in {
        PROVIDER_MISMATCH_REASON,
        MODEL_MISMATCH_REASON,
        DIMENSION_MISMATCH_REASON,
    }:
        return RetrievalFilteredReason.INCOMPATIBLE_INDEX
    return RetrievalFilteredReason.UNKNOWN


def _evidence_trace_key(evidence) -> tuple[object, ...]:
    if evidence.citation_unit_id is not None:
        return ("citation_unit", evidence.citation_unit_id)
    if evidence.chunk_db_id is not None:
        return ("chunk_db", evidence.chunk_db_id)
    return ("chunk", evidence.document_id, str(evidence.chunk_id))


def _coerce_scope(value: object) -> KnowledgeBaseScope:
    if isinstance(value, KnowledgeBaseScope):
        return value
    return KnowledgeBaseScope(str(value))


def _coerce_review_status(value: object) -> DocumentReviewStatus:
    if isinstance(value, DocumentReviewStatus):
        return value
    return DocumentReviewStatus(str(value))


def _select_context_chunks(raw_chunks, *, question: str | None = None):
    from app.services.qa import select_context_chunks_for_answer

    return select_context_chunks_for_answer(raw_chunks, question=question)


def _select_evidence_units(
    *,
    db,
    query: str,
    context_chunks,
    max_evidence_units: int,
    use_query_evidence_profile: bool = True,
):
    from app.services.qa import (
        build_citation_ready_fallback_units,
        load_citation_units_for_chunks,
        select_evidence_units,
    )

    chunk_units = load_citation_units_for_chunks(db=db, chunks=context_chunks)
    diagnostics: dict[str, object] = {}
    selected = select_evidence_units(
        question=query,
        retrieved_chunks=context_chunks,
        chunk_units=chunk_units,
        max_evidence_units=max_evidence_units,
        use_query_evidence_profile=use_query_evidence_profile,
        diagnostics=diagnostics,
    )
    if selected:
        return selected, diagnostics

    analysis = analyze_evidence_query(query)
    if analysis.query_type == EVIDENCE_QUERY_ATTRIBUTE:
        return [], diagnostics

    fallback = build_citation_ready_fallback_units(
        question=query,
        retrieved_chunks=context_chunks,
        chunk_units=chunk_units,
        max_evidence_units=max_evidence_units,
    )
    selection = diagnostics.get("evidence_selection")
    if isinstance(selection, dict):
        selection["selected_count"] = len(fallback)
        selection["fallback_used"] = True
    return fallback, diagnostics


def _align_raw_items_to_evidences(*, items, evidences):
    if not items:
        return []
    item_by_key = {
        _raw_item_key(item): item
        for item in items
    }
    aligned = []
    for evidence in evidences:
        item = item_by_key.get(_evidence_key(evidence))
        if item is not None:
            aligned.append(item)
    return aligned


def _raw_item_key(item) -> tuple[int, str, int | None]:
    return (
        int(getattr(item, "document_id")),
        str(getattr(item, "chunk_id")),
        getattr(item, "citation_unit_id", None),
    )


def _evidence_key(evidence) -> tuple[int, str, int | None]:
    return (
        evidence.document_id,
        str(evidence.chunk_id),
        evidence.citation_unit_id,
    )


def _annotate_graph_evidences(evidences, *, graph_chunk_keys):
    if not graph_chunk_keys:
        return evidences
    annotated = []
    for evidence in evidences:
        if (evidence.document_id, str(evidence.chunk_id)) not in graph_chunk_keys:
            annotated.append(evidence)
            continue
        graph_score = evidence.final_score
        annotated.append(
            evidence.model_copy(
                update={
                    "graph_score": graph_score,
                    "final_score": graph_score if graph_score is not None else evidence.final_score,
                    "metadata": {
                        **evidence.metadata,
                        "source": "graph_vector_mix",
                    },
                }
            )
        )
    return annotated


def _annotate_chunk_score_evidences(evidences, *, chunks, retrieval_mode: RetrievalMode):
    if not chunks:
        return evidences

    chunk_by_key = {}
    for chunk in chunks:
        if getattr(chunk, "chunk_db_id", None) is not None:
            chunk_by_key[("chunk_db", chunk.chunk_db_id)] = chunk
        chunk_by_key[("chunk", chunk.document_id, str(chunk.chunk_id))] = chunk

    annotated = []
    for evidence in evidences:
        chunk = None
        if evidence.chunk_db_id is not None:
            chunk = chunk_by_key.get(("chunk_db", evidence.chunk_db_id))
        if chunk is None:
            chunk = chunk_by_key.get(("chunk", evidence.document_id, str(evidence.chunk_id)))
        if chunk is None:
            annotated.append(evidence)
            continue

        metadata = {
            **evidence.metadata,
            "candidate_sources": list(chunk.candidate_sources or ()),
            "matched_terms": list(chunk.matched_terms or ()),
            "retrieval_mode": retrieval_mode.value,
        }
        annotated.append(
            evidence.model_copy(
                update={
                    "vector_score": chunk.vector_score,
                    "keyword_score": chunk.keyword_score,
                    "graph_score": chunk.graph_score or evidence.graph_score,
                    "final_score": chunk.score,
                    "metadata": metadata,
                }
            )
        )
    return annotated
