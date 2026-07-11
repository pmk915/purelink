# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project intends to use Semantic Versioning after the first tagged release.

## [Unreleased]

### Added

- Added a deterministic cross-domain RAG generalization eval corpus, JSONL
  cases, evidence-level metrics, run metadata, summary generation, and
  `make eval-rag-generalization`.

### Changed

- Improved citation-unit granularity by preserving source-span metadata across
  fixed and block-aware chunking, including page/section locators and field
  boundaries. Already processed documents must be reprocessed and reindexed to
  use the new citation units; no database migration is required.

### Fixed

- Improved rule-based auto retrieval routing with explicit confidence,
  routed/effective mode metadata, and conservative graph/hybrid fallbacks.
