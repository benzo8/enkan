# Changelog

This file summarizes user-facing and project-shaping changes across the practical release history of enkan.

It is intentionally concise. Detailed engineering-level change history remains in Git commit history.

## 2.5.0

- Reworked `controlled_random_weighted` (`CRW`) around logical image-bearing tree nodes and balanced-branch buckets, making provider activation fast on very large shows while preserving tree-derived weights.
- Added runtime provider metadata and selection scopes so cache preloading, CRW memory, and status overlays stay aligned with the media actually shown.
- Improved slideshow advance responsiveness by avoiding full root-scope snapshot copies on every weighted image advance.
- Preserved Branch/Folder navigation correctly when leaving Parent Mode after changing navigation basis.
- Improved stale `.tree` handling by repairing runtime indexes in memory before falling back to rebuilding from source files.
- Continued the 2.5 engineering refactor by extracting media file operations, status-bar formatting, explicit navigation types, and scope state helpers out of the slideshow monolith.

## 2.5.0-rc2

- Reworked `controlled_random_weighted` (`CRW`) to build its runtime index from logical image-bearing tree nodes instead of scanning the flattened media list when the provider is activated.
- Added a richer runtime selection model so providers can consume both the flattened media pool and node-level selection units without pushing CRW-specific logic back into the slideshow.
- Changed CRW memory keys from raw filesystem folders to provider-neutral node identities, which keeps flattened nodes as one shared memory unit and preserves future provider extensibility.
- Threaded provider pick metadata through the preload/cache path so runtime memory and status reporting stay aligned with what the viewer actually sees.
- Improved stale `.tree` handling by wiring in-memory pickle repair back into the multi-source load path before falling back to rebuilding from source files.

## 2.4.9

- Merged the long-running `dev` work into the first public `2.4` release line.
- Added the `controlled_random_weighted` (`CRW`) provider with folder-level recency control, streak suppression, persistent runtime memory, and provider comparison tooling via `--test` plus `--tm`.
- Preserved viewer history across temporary `SUB` and `PAR` scope changes so back/forward navigation follows what the user actually saw.
- Hardened multi-input and merge handling, including nested input resolution, source-local parsing scope, and specific-image replacement during merge.
- Improved runtime responsiveness with better cache/queue semantics, real video caching, and a typed slideshow scope stack.
- Cleaned up diagnostics, slideshow internals, and release/documentation infrastructure for the modern 2.x line.

## v2.0.3

- Polished the 2.0 line after the first multi-input merge wave.
- Updated installation and packaging documentation on `main`.

## v2.0.2

- Advanced the 2.0 series integration work and merged a substantial `dev` line back into `main`.
- Continued the shift toward the modern tree/input/runtime structure used by current releases.

## v2.0.1

- Honoured existing EXIF orientation on load and added EXIF orientation writing for persisted image rotation.
- Added the `Ctrl-R` rotation persistence workflow for images.

## 2.0.0

- Established the modern 2.x codebase through a major `dev` merge.
- Consolidated the Tkinter slideshow, tree-building pipeline, and packaged CLI/app structure.

## v1.96

- Allowed users to write reusable `.tree` snapshots for faster reloads and distribution.
- Added the load/save tree workflow that later became the `--outputtree` path.

## v1.40-dev

- Added video playback support to the slideshow runtime.
- Added video-aware input parsing and weighting so shows could mix images and videos.
- Continued modularisation work and prepared the codebase for larger architectural refactors.

## v1.30

- Added multi-mode behavior and expanded mode handling beyond the earlier single-mode model.

## v1.10

- Added groups and proportions.
- Strengthened branch-level weighting control and show composition.

## v1.00

- Added grafting and more structured modifier management.
- Marked the first broadly recognisable version of the tree/modifier-driven slideshow model.

## v0.50 to v0.99

- Introduced the tree and treenode model.
- Moved more weighting logic into tree building.
- Added defaults, filters, stack-based branch following, and improved filename/subfolder behavior.
- Refined weighting, balancing, mode parsing, and testing support.

## v0.10 to v0.40

- Added history, test tooling, subfolder mode, random mode, filename display improvements, rotation, and balanced-vs-weighted behavior.
- Iterated rapidly on modifier handling and slideshow interaction.

## v0.01

- Initial public version of the slideshow project.
