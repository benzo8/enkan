# Combining multiple inputs, of potentially different types

## Breakdown

### Goals

- Fully automated testing, standardised testing of every input combination, including .txt files which do and do not contain grafting and groups, IrfanView-style and enkan-style .lst files and current PICKLE Version .trees.
- Automated testing of balanced harmonisation across all input combinations, including adherence to global mode divined from command-line and first (left-most) input file to contain a global mode modifier.

### Status

- ✓ Single dispatcher: `tree_logic.build_tree` routes txt/lst; `.tree` via `tree_io.load_tree_if_current`.
- ✓ InputProcessor slimmed for txt; nested handler used by MultiSourceBuilder.
- ✓ Stage 1 ingestion in MultiSourceBuilder: capture mode/lowest_rung/graft_offset/group/warnings for all inputs (including nested) without harmonising mid-loop.
- ✓ Stage 2 merge: target mode chosen CLI -> first mode-bearing source; graft_offset computed vs target lowest rung; TreeMerger applies offsets at leaf level (group-aware) and merges by path, then one global `apply_mode_and_recalculate`.
- ✓ TreeBuilderTXT writes group metadata to nodes; TreeNode carries group; TreeMerger grafting uses it.
- ✓ TreeBuilderLST: records weights on nodes and infers balanced rung with confidence (warns when <100%).
- ✓ Logging: numeric verbosity flag replaces debug/quiet; MultiSourceBuilder logs at info/warn.
- ➜ Progress bars: tqdm for lst; quiet/leave handling still deferred.
- ➜ Tests/QA: to add (see below).
- ➜ Docs/notes: this plan/architecture updated; README/help still to refresh.

### Open questions

- Finalise .lst semantics: unweighted lists rely on global mode; weighted lists lose proportions on global recalc—confirm acceptability.
- Warnings: nested/stale inputs now bubble up and are deduped; still need structured metadata and optional escalation (deferred).
- Consider quiet/leave behaviour for tqdm (TXT/LST) once CLI quiet flag returns.

## Issues combining each combination

### .txt + .txt

.txt files can contain global information. At the moment we ignore global information in the second and subsequent .txt files. We should try to harmonise the information in files, such that the initial global information remains relevant to later files. If the global setting in _file 1_ is [b4] and the global setting in _file 2_ is [b5] we graft the entries in _file 2_ such that their lowest-rung balance level is also [b4]. Duplicates should be handled gracefully, including being grafting aware so we don't duplicate a folder moved from its original location in _file 1_ with the same folder in _file 2_. (Current TreeMerger aligns lowest rung via graft_offset and merges by path; needs automated coverage.)

### .tree + .tree

.tree's should be merged, with the _tree 1_ being the arbiter of truth when it comes to the __location__ of duplicates and _tree 2_ being the arbiter of truth when it comes to the __content__ of branches.

### .tree + .txt

As per above, _tree 1_ should be the arbiter of truth when it comes to the __location__ of duplicates and __file 1__ should be the arbiter of truth when it comes to the __content__ of branches. This way, a large tree could be edited with, for example updated or additional files, by adding .tree + .txt.

### .txt/.tree + .lst

Type (a) lists do not contain the full information to recreate a tree. We have a list of file paths/names and their weights. We could recreate a tree from the file paths, fill each end with files, add up each folders weights and pass them back up the tree, recreating everything except grafting.
Type (b) lists do not contain the full information to recreate a tree. We have a list of file paths/names. We could recreate a tree from the file paths and fill each end with files. If we are given a mode string, we could assign weights based on that.

Either of these could then be merged with an existing (or calculated) tree, paying attention to duplicates as before.

## Further Considerations

- This is related to the "(Re-)calculating Weight On The Fly" work done in the dev-user_proportion branch. We'll probably want to merge that into this step.
- Whatever we are loading, we should ensure we backfill as much information as we can infer.
- More than two additions work from left to right (((a + b) + c) + d), etc.
- The order of truth for global mode is: command-line argument -> the first tree (PICKLE 3 records the original mode-string) -> the first .txt global mode modifier. We recalculate weights once at the end under that mode.
- Grafting to match a previous tree might drop files below the lowest_rung, where balancing makes no sense. We now warn and abort on that path.
- Automated suite next: cover all input combinations (txt/txt, tree/tree, tree/txt, txt/tree + lst weighted/unweighted, nested) for mode alignment, graft offsets, group-aware grafting, duplicate handling, and warning propagation.
