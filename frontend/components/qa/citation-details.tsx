import type { CitationLike } from "@/types";

export function getCitationDisplayDetails(citation: CitationLike) {
  const locator = citation.source_locator;
  const pageNumber = firstNumber(locator?.page_number, citation.page_number);
  const charStart = firstNumber(locator?.char_start, citation.char_start);
  const charEnd = firstNumber(locator?.char_end, citation.char_end);
  const hasCharRange =
    typeof charStart === "number" &&
    typeof charEnd === "number" &&
    charStart >= 0 &&
    charStart < charEnd;
  const locatorHeadingPath = locator?.heading_path ?? [];

  return {
    sourceLabel: formatSourceLabel(citation.source_type),
    pageNumber,
    charStart: hasCharRange ? charStart : null,
    charEnd: hasCharRange ? charEnd : null,
    sectionTitle: locator?.section_title || citation.section_title,
    headingPath:
      locatorHeadingPath.length > 0 ? locatorHeadingPath : citation.heading_path,
    sourceLocatorText: locator?.source_locator_text ?? null
  };
}

export function formatSourceLabel(sourceType: string | null) {
  switch (sourceType) {
    case "pdf":
      return "PDF";
    case "markdown":
    case "md":
      return "Markdown";
    case "docx":
      return "DOCX";
    case "text":
    case "txt":
      return "Text";
    default:
      return sourceType ? sourceType.toUpperCase() : "Text";
  }
}

function firstNumber(...values: Array<number | null | undefined>) {
  return values.find((value): value is number => typeof value === "number") ?? null;
}
