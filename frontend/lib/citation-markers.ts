import type { Citation } from "@/types";

export type CitationAnswerSegment =
  | {
      type: "text";
      text: string;
    }
  | {
      type: "citation";
      text: string;
      marker: string;
      displayNumber: string;
      citation: Citation;
    };

const ANSWER_MARKER_PATTERN = /\[(S?[1-9]\d*)\]/gi;
const CITATION_MARKER_PATTERN = /^S([1-9]\d*)$/i;

export function parseCitationMarkers(
  answer: string,
  citations: Citation[]
): CitationAnswerSegment[] {
  const citationsByMarker = new Map<string, Citation>();

  for (const citation of citations) {
    const marker = normalizeCitationMarker(citation.citation_marker);
    if (marker && !citationsByMarker.has(marker)) {
      citationsByMarker.set(marker, citation);
    }
  }

  const segments: CitationAnswerSegment[] = [];
  let textStart = 0;

  for (const match of answer.matchAll(ANSWER_MARKER_PATTERN)) {
    const matchStart = match.index;
    const originalText = match[0];
    const markerToken = match[1];
    if (matchStart === undefined || !originalText || !markerToken) {
      continue;
    }

    const marker = normalizeAnswerMarker(markerToken);
    const citation = marker ? citationsByMarker.get(marker) : undefined;
    const isMarkdownLink = answer[matchStart + originalText.length] === "(";
    const isLikelyNumericIndex =
      !markerToken.toUpperCase().startsWith("S") &&
      isNumericIndexContext(answer, matchStart);
    if (!marker || !citation || isMarkdownLink || isLikelyNumericIndex) {
      continue;
    }

    if (matchStart > textStart) {
      segments.push({ type: "text", text: answer.slice(textStart, matchStart) });
    }
    segments.push({
      type: "citation",
      text: originalText,
      marker,
      displayNumber: marker.slice(1),
      citation
    });
    textStart = matchStart + originalText.length;
  }

  if (textStart < answer.length || segments.length === 0) {
    segments.push({ type: "text", text: answer.slice(textStart) });
  }

  return segments;
}

export function normalizeCitationMarker(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const normalized = value.trim().replace(/^\[|\]$/g, "");
  const match = normalized.match(CITATION_MARKER_PATTERN);
  return match ? `S${match[1]}` : null;
}

function normalizeAnswerMarker(value: string) {
  const canonical = normalizeCitationMarker(value);
  if (canonical) {
    return canonical;
  }
  return /^[1-9]\d*$/.test(value) ? `S${value}` : null;
}

function isNumericIndexContext(answer: string, markerStart: number) {
  const lineStart = answer.lastIndexOf("\n", markerStart - 1) + 1;
  if (answer.slice(lineStart, markerStart).trim() === "") {
    return true;
  }
  const previousCharacter = answer[markerStart - 1];
  return Boolean(previousCharacter && /[A-Za-z0-9_\])]/.test(previousCharacter));
}
