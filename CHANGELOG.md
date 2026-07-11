# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project intends to use Semantic Versioning after the first tagged release.

## [Unreleased]

### Added

### Changed

- Improved citation-unit granularity by preserving source-span metadata across
  fixed and block-aware chunking, including page/section locators and field
  boundaries. Already processed documents must be reprocessed and reindexed to
  use the new citation units; no database migration is required.

### Fixed
