import { expect, test } from "@playwright/test";

import { conversationMessageSchema } from "@/schemas/conversations";
import { askResponseSchema, citationSchema } from "@/schemas/qa";


const fullCitation = {
  citation_marker: "S1",
  document_name: "architecture.txt",
  text: "DocumentBlock preserves structure for retrieval.",
  source_type: "text",
  source_locator: {
    kind: "text_range",
    source_type: "text",
    source_locator_text: "section:Architecture",
    char_start: 10,
    char_end: 58,
    section_title: "Architecture",
    heading_path: ["PureLink", "Architecture"]
  },
  heading_path: ["PureLink", "Architecture"],
  section_title: "Architecture",
  page_number: null,
  char_start: 10,
  char_end: 58,
  citation_ready: true,
  retrieval_mode: "hybrid_text",
  score: 0.82
};


test("citation schema preserves complete public details without requiring internal ids", () => {
  const citation = citationSchema.parse(fullCitation);

  expect(citation.citation_marker).toBe("S1");
  expect(citation.document_name).toBe("architecture.txt");
  expect(citation.text).toBe(fullCitation.text);
  expect(citation.heading_path).toEqual(["PureLink", "Architecture"]);
  expect(citation.char_start).toBe(10);
  expect(citation.char_end).toBe(58);
  expect(citation.page_number).toBeNull();
  expect(citation.score).toBe(0.82);
  expect(citation.document_id).toBeNull();
  expect(citation.citation_unit_id).toBeNull();
});


test("citation schema normalizes legacy missing optional details", () => {
  const citation = citationSchema.parse({
    citation_marker: "S1",
    document_name: "legacy.txt",
    text: "Legacy citation text.",
    source_locator: null,
    score: null
  });

  expect(citation.heading_path).toEqual([]);
  expect(citation.source_locator).toBeNull();
  expect(citation.page_number).toBeNull();
  expect(citation.char_start).toBeNull();
  expect(citation.char_end).toBeNull();
  expect(citation.score).toBeNull();
  expect(citation.citation_ready).toBe(false);
});


test("citation schema preserves PDF pages and rejects malformed structural metadata", () => {
  const pageCitation = citationSchema.parse({
    citation_marker: "S2",
    document_name: "report.pdf",
    text: "Page evidence.",
    source_type: "pdf",
    page_number: 3,
    heading_path: [],
    citation_ready: true,
    retrieval_mode: "chunk_only",
    score: null
  });

  expect(pageCitation.page_number).toBe(3);
  expect(pageCitation.score).toBeNull();
  expect(() => citationSchema.parse({ ...fullCitation, heading_path: "Architecture" })).toThrow();
  expect(() => citationSchema.parse({ ...fullCitation, char_end: null })).toThrow();
});


test("personal team and conversation responses share the citation schema", () => {
  const personal = askResponseSchema.parse({
    conversation_id: 1,
    answer: "Supported [S1].",
    citations: [fullCitation]
  });
  const team = askResponseSchema.parse({
    conversation_id: 2,
    answer: "Supported [S1].",
    citations: [fullCitation]
  });
  const conversation = conversationMessageSchema.parse({
    id: 3,
    role: "assistant",
    content: "Supported [S1].",
    citations: [fullCitation],
    created_at: "2026-07-13T00:00:00Z"
  });

  expect(personal.citations[0]).toEqual(team.citations[0]);
  expect(personal.citations[0]).toEqual(conversation.citations[0]);
});
