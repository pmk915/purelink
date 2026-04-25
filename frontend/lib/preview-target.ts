import type {
  CitationLike,
  KnowledgeBaseScope,
  PreviewTarget,
  SourceLocator
} from "@/types";


export function formatMediaTime(seconds: number) {
  const normalized = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(normalized / 3600);
  const minutes = Math.floor((normalized % 3600) / 60);
  const remainingSeconds = normalized % 60;
  const minuteSecond = `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
  if (hours <= 0) {
    return minuteSecond;
  }
  return `${hours}:${minuteSecond}`;
}


export function resolvePreviewTarget(citation: CitationLike): PreviewTarget | null {
  if (citation.preview_target) {
    return citation.preview_target;
  }

  const locator = citation.source_locator;
  if (!locator) {
    return null;
  }

  return {
    kind: "document_preview",
    document_id: citation.document_id,
    source_type: citation.source_type,
    locator_kind: locator.kind,
    source_locator_text: locator.source_locator_text,
    char_start: locator.char_start,
    char_end: locator.char_end,
    section_title: locator.section_title,
    page_number: locator.page_number,
    start_time: locator.start_time,
    end_time: locator.end_time
  };
}


export function buildPreviewUrl(
  citation: CitationLike,
  options?: { scope?: KnowledgeBaseScope }
) {
  const scope = options?.scope ?? (citation.scope === "team" ? "team" : "personal");
  const previewTarget = resolvePreviewTarget(citation);
  if (!previewTarget) {
    return null;
  }

  const params = buildPreviewSearchParams({
    citation,
    locator: citation.source_locator,
    previewTarget
  });
  const basePath =
    scope === "team" && citation.team_id
      ? `/teams/${citation.team_id}/knowledge-bases/${citation.knowledge_base_id}/documents/${citation.document_id}/preview`
      : `/knowledge-bases/${citation.knowledge_base_id}/documents/${citation.document_id}/preview`;

  return `${basePath}?${params.toString()}`;
}


export function formatLocatorLabel(
  locator: SourceLocator | null,
  fallback: PreviewTarget | null,
) {
  const effective = locator ?? fallback;
  if (!effective) {
    return null;
  }

  if (typeof effective.page_number === "number") {
    return `Page ${effective.page_number}`;
  }

  if (
    typeof effective.start_time === "number" &&
    typeof effective.end_time === "number"
  ) {
    return `${formatMediaTime(effective.start_time)} - ${formatMediaTime(effective.end_time)}`;
  }

  if (effective.section_title) {
    return effective.section_title;
  }

  if (
    typeof effective.char_start === "number" &&
    typeof effective.char_end === "number"
  ) {
    return `Characters ${effective.char_start}-${effective.char_end}`;
  }

  return effective.source_locator_text;
}


function buildPreviewSearchParams({
  citation,
  locator,
  previewTarget
}: {
  citation: CitationLike;
  locator: SourceLocator | null;
  previewTarget: PreviewTarget;
}) {
  const params = new URLSearchParams();
  params.set("chunk_id", citation.chunk_id);
  params.set("locator_kind", previewTarget.locator_kind);
  setParam(params, "source_type", previewTarget.source_type);
  setParam(params, "locator", previewTarget.source_locator_text);
  setParam(params, "page", previewTarget.page_number);
  setParam(params, "char_start", previewTarget.char_start);
  setParam(params, "char_end", previewTarget.char_end);
  setParam(params, "start_time", previewTarget.start_time);
  setParam(params, "end_time", previewTarget.end_time);
  setParam(params, "section", previewTarget.section_title);

  if (locator?.heading_path?.length) {
    params.set("heading_path", locator.heading_path.join("/"));
  }

  return params;
}


function setParam(
  params: URLSearchParams,
  key: string,
  value: string | number | null | undefined,
) {
  if (value === null || value === undefined || value === "") {
    return;
  }
  params.set(key, String(value));
}
