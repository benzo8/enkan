# Enkan Architectural & Responsibility Map (Agents)

This document describes the major "agents" (modules/classes/subsystems) in Enkan, their responsibilities, boundaries, and interaction patterns. Treat each agent as an autonomous unit with a clear contract.

> NOTE: “Agent” here is conceptual: a cohesive unit with inputs, outputs, side‑effects, and invariants.

---

## 1. Core Data & Domain Agents

### 1.1 Tree / TreeNode

- Purpose: Hierarchical representation of directories, files, synthetic grouping, and applied modifiers.
- Inputs: Parsed list entries, merged trees, runtime transformations (mode adjustments).
- Outputs: Provides traversal, weight maps, branch statistics.
- Invariants:
  - Root node name constant: `ROOT_NODE_NAME`.
  - Each node has a stable path key (canonicalized).
  - `path_lookup` is the canonical map for locating nodes from filesystem paths; once a path is registered it is treated as definitive for that runtime (only deliberate file deletions may alter membership).
  - Many-to-one mappings in `path_lookup` are permitted (flattened/grafted/grouped branches); resolving a filesystem path via `path_lookup` must return the node that currently owns that path’s files.
- Responsibilities:
  - Maintain `path_lookup` for O(1) node resolution. (TODO: confirm implemented)
  - Expose method to recalculate weights.
- [TODO: USER: Add any missing Tree invariants, e.g. graft level semantics]

### 1.2 Defaults

- Purpose: Global / cascading defaults (mode, video/mute policy, recursion filters).
- Inputs: Parsed global directives (`*` lines), CLI flags.
- Outputs: Base configuration consumed by processors and tree builders.
- [TODO: USER: Enumerate all mutable default fields]

### 1.3 Filters

- Purpose: Inclusion/exclusion logic (must contain, must not contain, skip recursion flags).
- Inputs: List modifiers ([+], [-], [/], etc.).
- Outputs: Predicate checks used during file enumeration.
- [TODO: USER: Clarify precedence rules between ignore vs must-contain]

### 1.4 Mode System

- Purpose: Determines how selection modes (balanced, weighted, random, etc.) apply across depth levels.
- Inputs: Parsed mode strings (`[b0,0]`, `[w2,-1]` sequences).
- Outputs: Structured mode modifier applied in weight calculation.
- [TODO: USER: Document exact grammar for mode tokens]

---

## 2. Input & Build Agents

### 2.1 MultiSourceBuilder

- Purpose: Orchestrate building multiple trees and merge them.
- Inputs: Ordered list of input file paths.
- Outputs: Single merged `Tree`, aggregated warnings.
- Behavior:
  - Deterministic left-to-right merge: (((a + b) + c) + d).
  - Global mode precedence: CLI flag > left-most input containing a global mode string (PICKLE `.tree` stored mode or `.txt` global) > no harmonisation. Later inputs align/graft to the established baseline.
  - Delegates warnings from builders/merger upward with source context.
- Roadmap:
  - Support directory expansion / globbing.
  - Normalize paths before dispatch to stabilize `path_lookup` resolution.

### 2.2 TreeBuilderTXT

- Purpose: Materialise a tree from a .txt files, or from direction path information in command-line input.
- Description of .txt files:
  - These are the bread and butter of enkan. They describe exactly how a new tree should be built
  - Slow to load (requires scanning the entire described folder structure, loading all the found files, grafting as required and calculating weights)
  - Offers node-based navigation and full balancing control
  - They contain global and local information
  - They can contain other text files
  - Multiple -i command-line arguments are the equivalent of a .txt file containing the same lines

### 2.3 TreeBuilderLST

- Purpose: Materialise a tree from a .lst file.
- Decription of .lst files:
  a) Enkan-weighted lists: each line is `file_path` plus newline-separated weight.
  - Fast to load (paths + weights to internal structures)
  - (Currently) Does not create a tree and so offers no access to node-based navigation

  b) Standard lists of files, as per irfanView for example. These contain file-paths delineated by a newline, but no weighting.
  - Fast to load (loads text file of paths directly into internal structures, adds constant weight or mode-derived weight)
  - Offers no balancing; is effectively mode w1 by necessity unless a mode string is supplied
  - Does not create a tree and so offers no access to node-based navigation
  - Merging behavior: when combined with existing trees, use `path_lookup` to place files; if mode present, align with established global mode precedence.

### 2.4 InputProcessor

- Purpose: Parse a single input source (.txt file describing multiple directories, or single directory).
- Responsibilities:
  - Tokenize `[modifier]` groups.
  - Dispatch modifier handlers (weight, proportion, graft, group, mode override, flat, video/mute toggles, recurse restrictions).
  - Emit `(Tree, warnings)` (post-refactor target).
- Side Effects:
  - Mutates `defaults` for global directives.
  - Updates `filters`.
- [TODO: USER: List all recognized modifier patterns and their precedence]

### 2.4 TreeMerger

- Purpose: Combine two trees:
  - Handle graft level conflicts.
  - Merge metadata (mode modifiers, proportions).
  - Field precedence:
    - Left-most (earlier) input is authoritative for `node.name` and base location (pre-graft/group).
    - Right-most (later) input is authoritative for `user_proportion`, `weight_modifier`, `is_percentage`, `images`, and additional location metadata (graft/group attachments).
  - Merge data: later input wins file-content truth for that path; add new files and remove missing files scoped to the current `path_name` even when the node is shared (flattened/grafted/grouped).
  - Preserve branch integrity.
  - Use `path_lookup` to resolve destination nodes; if a later input's path resolves to an existing node, the later input's files from that path replace earlier files from that same path while leaving other aliases in the node intact.
  - Emit structured warnings for conflicts (graft level, mode collisions, missing paths) with source attribution for MultiSourceBuilder to bubble up.
- Optimization Targets:
  - Replace linear child scans with `path_lookup`.
  - Reduce deep recursion duplication.
- [TODO: USER: Define conflict resolution policy for duplicate file nodes]

---

## 3. Selection & Weight Agents

### 3.1 Weight Calculator

- Purpose: Translate node metadata + mode modifiers into final per-image weights.
- Inputs: Tree structure, mode layers, proportions.
- Outputs: List of `(image_path, weight)` ready for cumulative distribution.
- Performance Notes:
  - Cache intermediate branch sums if repeatedly recalculated.
  - Consider lazy recalculation on mutation.
- [TODO: USER: Specify algorithm steps for weight normalization]

### 3.2 Extraction Logic (`extract_image_paths_and_weights_from_tree`)

- Purpose: Flatten tree to ordered image list & aligned weights.
- Must Guarantee:
  - Stable ordering under identical tree structure.
  - Consistent length alignment (len(images) == len(weights)).
- [TODO: USER: Confirm treatment of video files here]

---

## 4. Runtime / Interaction Agents

### 4.1 CLI

- Purpose: User entry point; argument parsing; orchestration.
- Responsibilities:
  - Normalise inputs.
  - Send inputs to MultiSourceBuilder.
  - Perform unified extraction.
  - Optionally print tree information.
  - Call start_slideshow()
- [TODO: USER: Add future planned flags]

### 4.2 GUI (Gui class)

- Purpose: Centralized abstraction for UI dialogs (Tk / CustomTk / CTkMessagebox).
- Exposed Methods:
  - `messagebox(...)`
  - Factory: `create_mode_adjust_dialog(...)`
  - Centering, sizing heuristics.
- Future Planned Widgets:
  - tqdm overloaded Progress Bar:
    - Single call, invokes both console and tkinter tqdm depending on quiet flag and whether tkinter is active.

### 4.3 ModeAdjustDialog

- Purpose: Interactive editing of internal mode structure.
- Dependencies:
  - Needs `Gui.messagebox` for error display.
  - Talks to slideshow controller for apply/reset.
- [TODO: USER: Add validation rules for mode syntax]

### 4.4 ImageSlideshow

- Purpose: Event loop for displaying images/videos; invokes cache, zoom/pan, rotation, EXIF updates.
- Core Methods (examples):
  - `_show_error`, `_confirm_action`, rotation handlers.
  - `_write_exif_orientation`: updates orientation tag when rotation persists.
- [TODO: USER: Clarify lifecycle (init → load list → start loop)]

### 4.5 Cache / ImageCacheManager

- Purpose: Preload / retain decoded image data to improve frame advance latency.
- Considerations:
  - Memory bounds / LRU strategy (if not present, plan).
  - Threading? (Background decode)
- [TODO: USER: Document eviction strategy]

### 4.6 ZoomPan

- Purpose: Encapsulate transformations for displayed images in GUI.
- [TODO: USER: Note supported gestures / keyboard shortcuts]

---

## 5. Media / Metadata Agents

### 5.1 EXIF Handler

- Purpose: Read/write orientation tag (0x0112).
- Constraints:
  - Only rotates when angle multiple of 90.
  - Requires Pillow build with Exif support.
- [TODO: USER: Decide if lossless rotate or metadata-only]

### 5.2 Video Handler (VLC integration)

- Purpose: Play videos inline in slideshow.
- Questions:
  - Videos are weighted the same as images
  - Skip logic when user disables videos globally but explicit path present?
- [TODO: USER: Define video autoplay vs manual advance behavior]

---

## 6. Error / Warning Agents

### 6.1 Warning Aggregator

- Current: Ad hoc lists returned from builders/processors.
- Target:
  - Central collector (class) with severity + origin.
  - Optional CLI flag to escalate warnings to errors.
- [TODO: USER: Specify priority escalation policy]

### 6.2 Logging Strategy

- Recommendation:
  - Use `__name__` for hierarchical loggers.
  - Provide a verbose flag to include merge diagnostics.
- [TODO: USER: List desired log categories (parse, merge, gui, media, cache)]

---

## 7. Planned / Future Agents

| Agent | Purpose | Status |
|-------|---------|--------|
| DirectoryScanner | Recursive, filter-aware population | [TODO: USER: Confirm need] |
| GlobResolver | Support wildcards in list files | Planned |
| Test Suite (pytest) | Validate merge, mode parsing, weighting | Partial |
| MetricsCollector | Performance counters (cache hits, decode times) | Future |
| SessionState | Persist user adjustments (mode edits, rotation) | Future |

---

## 8. Interaction Overview (Data Flow)

1. CLI parses args.
2. MultiSourceBuilder produces `Tree`.
3. TreeMerger (if multi) consolidates nodes.
4. Extraction → `(images, weights)` → cumulative weights.
5. Slideshow loop consumes images:
   - Cache manager retrieves / decodes.
   - GUI displays; ZoomPan transforms.
   - User rotates → EXIF handler may persist.
6. Mode adjust dialog can mutate defaults/mode → triggers weight recalculation.

[TODO: USER: Add diagram or sequence chart if desired]

---

## 9. Cross-Cutting Concerns

- Thread Safety:
  - UI is single-threaded.
  - IO is configurable (currently in code only) between single-threaded or background loading.
    - constants.py: PRELOAD_QUEUE_LENGTH = 3
- Performance Hotspots:
  - Tree merge deep traversal (optimize via `path_lookup`).
  - Weight recalculation (memoize unchanged branches).
- Configuration Persistence: [TODO: USER: Decide format (JSON, YAML, INI) for user preferences]
- Extensibility:
  - Pluggable weight strategies.
  - Custom filters (user-defined predicates).

---

## 10. Open Questions (Need Your Input)

1. Should directory inputs fully expand recursively by default? [TODO]
2. How to treat explicit video file when global videos disabled? [TODO]
3. Are group proportions mutually exclusive or blended? [TODO]
4. Should grafted branches inherit parent mode or override entirely? [TODO]
5. Define precise semantics for `flat` on directories. [TODO]
6. Provide CLI flag for saving modified mode back into a list file? [TODO]
7. Confirm expected behavior for duplicate paths across multiple input lists. [TODO]

---

## 11. Glossary (Fill Out)

| Term | Definition |
|------|------------|
| Graft Level | [TODO: USER] |
| Mode Modifier | [TODO: USER] |
| Proportion | [TODO: USER] |
| Flat Directory | [TODO: USER] |
| Graft Offset | [TODO: USER] |

---

## 12. Validation & Testing Targets

| Test Category | Examples |
|---------------|----------|
| Modifier Parsing | Weight %, graft, group, mode, video/mute flags |
| Merge Conflicts | Same path different graft level, mode merge |
| Weight Stability | Recalc after mode change yields deterministic ordering |
| GUI Dialogs | Centering, messagebox fallback behavior |
| EXIF Write | Correct orientation applied only at multiples of 90 |

[TODO: USER: Add additional categories]

---

## 13. Maintenance Notes

- Prefer additive handlers over if/elif chains for modifiers.
- Keep constants central in `constants.py` (regex, root node name).
- Avoid magic strings (“root”) outside constants.
- Use builtin generics (`list[str]`) consistently.
- Log warnings through a single collection agent (future).

---

## 14. Actionable Next Steps (Initial Roadmap)

| Priority | Task |
|----------|------|
| High | Add unit tests for tree merging |
| High | Optimize node lookup with `path_lookup` |
| Medium | Formalize ListTreeBuilder class usage |
| Medium | Centralize warning aggregation |
| Low | Introduce session persistence |
| Low | Add performance metrics hooks |

[TODO: USER: Adjust priorities]

---

## 15. Revision History

| Date | Author | Summary |
|------|--------|---------|
| 2025-11-23 | Initial scaffold | Agent framework created |
| [TODO] | [TODO] | Updates applied |

---

## 16. Final Integration Checklist (Before Major Version Increment)

- [ ] Unified `(Tree, warnings)` everywhere
- [ ] Mode editor updates weights dynamically
- [ ] Path lookup optimized in merge
- [ ] Directory recursive expansion implemented or deferred explicitly
- [ ] Unit test coverage ≥ target threshold [TODO: USER: define %]
- [ ] README and docs reflect multi-source behavior

---

> Fill in all [TODO: USER] markers to finalize this document.
