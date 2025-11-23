# Input layer consolidation plan

Context

- Current spread: InputProcessor handles line parsing + extension dispatch; MultiSourceBuilder orchestrates multi-source flow/mode harmonisation; list_tree_builder rebuilds .lst into Trees.
- Goal: one entry point that accepts .tree/.lst/.txt (incl. nested) and returns a Tree; reduce duplication and simplify cli.

Principles

- Keep filesystem/extension concerns in utils/input; keep tree/TreeBuilder/tree_logic pure tree operations.
- Preserve mode harmonisation/graft offsets and filter/global directives; no behavioural regressions on modifiers.
- Prefer stateless helpers reusable by MultiSourceBuilder; InputProcessor becomes thin or goes away.

Plan (status)

- ✅ Move tree/lst dispatch into MultiSourceBuilder and tree_logic: dispatcher build_tree in tree_logic, TreeBuilderLST in tree/, .tree loading via tree_io.load_tree_if_current; mode harmonisation intact.
- ✅ Extract parsing helpers / slim InputProcessor: now txt-only parser with nested handler hook; private _process_entry recursion.
- ✅ Unify recursion: MultiSourceBuilder supplies nested_file_handler for nested .lst/.tree, merges resulting trees, recalculates weights; TreeBuilder.py removed.
- ✅ CLI path simplified to always use MultiSourceBuilder (merge flag commented out).
- ✅ Progress bars: tqdm added to .lst builder; future quiet handling deferred.
- ⏳ Tests/QA: add regression for directives ([r], [+]/[-], "*" globals), mode detection/graft offsets, list rebuild (pre-weighted vs unweighted), nested txt/lst/tree, flat dirs, specific images; smoke slideshow/test distribution.
- ⏳ Docs/notes: update README/help to describe single dispatcher, nested handling, stale .tree behaviour, progress bar/quiet flag handling.

Open questions

- Finalise .lst semantics: pre-weighted vs unweighted behaviour and mode inheritance when merged; ensure proportions match expectations.
- Propagate/handle warnings from nested merges and weight recalcs back to CLI.
- Consider quiet/leave behaviour for tqdm (TXT/LST) once CLI quiet flag is reintroduced.
