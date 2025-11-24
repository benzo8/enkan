# Combining multiple inputs, of potentially different types

## Breakdown

### Goals

- Fully automated testing, standardised testing of every input combination, including .txt files which do and do not containing grafting and groups, IrfanView-style and enkan-style .lst files and current PICKLE Version .trees.
- Automated testing of balanced harmonisation across all input combinations, including adherence to global mode divined from command-line and first (left-most) input file to contain a global mode modifier.

### Status

- ✅ Move tree/lst dispatch into MultiSourceBuilder and tree_logic: dispatcher build_tree in tree_logic, TreeBuilderLST in tree/, .tree loading via tree_io.load_tree_if_current; mode harmonisation intact.
- ✅ Extract parsing helpers / slim InputProcessor: now txt-only parser with nested handler hook; private _process_entry recursion.
- ✅ Unify recursion: MultiSourceBuilder supplies nested_file_handler for nested .lst/.tree, merges resulting trees, recalculates weights; TreeBuilder.py removed.
- ✅ CLI path simplified to always use MultiSourceBuilder (merge flag commented out).
- ✅ Progress bars: tqdm added to .lst builder; future quiet handling deferred.
- ⏳ Tests/QA: add regression for directives ([r], [+]/[-], "*" globals), mode detection/graft offsets, list rebuild (pre-weighted vs unweighted), nested txt/lst/tree, flat dirs, specific images; smoke slideshow/test distribution.
- ⏳ Docs/notes: update README/help to describe single dispatcher, nested handling, stale .tree behaviour, progress bar/quiet flag handling.

### Open questions

- Finalise .lst semantics: pre-weighted vs unweighted behaviour and mode inheritance when merged; ensure proportions match expectations.
- Propagate/handle warnings from nested merges and weight recalcs back to CLI.
- Consider quiet/leave behaviour for tqdm (TXT/LST) once CLI quiet flag is reintroduced.

## Issues combining each combination

### .txt + .txt

.txt files can contain global information. At the moment we ignore global information in the second and subsequent .txt files.
We should try to harmonise the information in files, such that the initial global information remains relevant to later files.
What I mean by this is if the global setting in _file 1_ is [b4] and the global setting in _file 2_ is [b5] we graft the entries in _file 2_ such that their lowest-rung balance level is also [b4].
Duplicates should be handled gracefully, including being grafting aware so we don't duplicate a folder moved from it's original location in _file 1_ with the same folder in _file 2_

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
- Whatever we are loading, we should ensure we backfill as much information as we can infer
- More than two additions work from left to right (((a + b) + c) + d), etc.
- The order of truth for global mode is: command-line argument -> the first tree (PICKLE 3 records the original mode-string) -> the first .txt global mode modifier. We should recalculate weights to the right as required.
- Grafting to match a previous tree might drop files below the lowest_rung, where balancing makes no sense. We will need to handle that.
