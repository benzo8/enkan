# Input layer consolidation plan

Context

- Current spread: InputProcessor handles line parsing + extension dispatch; MultiSourceBuilder orchestrates multi-source flow/mode harmonisation; list_tree_builder rebuilds .lst into Trees.
- Goal: one entry point that accepts .tree/.lst/.txt (incl. nested) and returns a Tree; reduce duplication and simplify cli.

Principles

- Keep filesystem/extension concerns in utils/input; keep tree/TreeBuilder/tree_logic pure tree operations.
- Preserve mode harmonisation/graft offsets and filter/global directives; no behavioural regressions on modifiers.
- Prefer stateless helpers reusable by MultiSourceBuilder; InputProcessor becomes thin or goes away.

Plan

1) Baseline behaviour: capture sample inputs (.tree/.lst/.txt with globals, nested txt, filters, grafts, flat, video/mute) and add regression tests where feasible.
2) Move tree/lst dispatch into MultiSourceBuilder: adopt _load_tree_if_current, call build_tree_from_list, keep mode detection/harmonisation; warn/skip stale .tree.
3) Extract parsing helpers: new module (e.g., tree_builders.py) exposing parse_input_line/parse_input_file → image_dirs/specific_images; migrate from InputProcessor.process_entry/process_input.
4) Unify recursion: MultiSourceBuilder._build_tree_from_entry re-enters builder for nested files instead of processor recursion; ensure graft_offset propagates.
5) Simplify InputProcessor or remove: leave thin shim if legacy callers; otherwise delete and update imports.
6) CLI cleanup: always use MultiSourceBuilder; remove merge_required/InputProcessor path; keep output tree/list writing working.
7) Tests/QA: cover directives ([r], [+]/[-], "*" globals), mode detection, graft offsets, list rebuild, nested txt, flat dirs, specific images; smoke slideshow/test distribution.
8) Docs/notes: update README/help strings to describe single entry point and behaviour for .tree/.lst/.txt.

Open questions

- Keep build_tree_from_list in utils/input or move beside tree builders?
- Any external callers of InputProcessor needing a shim?
- Keep warning on flat list-only inputs or auto-tree with default proportions?
