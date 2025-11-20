# Next Step

## Combining multiple inputs, of potentially different types

### Breakdown

Currently we have three main input types:

1. .txt files

   * These are the bread and butter of enkan. They describe exactly how a new tree should be built
   * Slow to load (requires scanning the entire described folder structure, loading all the found files, grafting as required and calculating weights)
   * Offers node-based navigation and full balancing control
   * They contain global and local information
   * They can contain other text files
   * Multiple -i command-line arguments are the equivalent of a .txt file containing the same lines

2. .lst files
   These come in two forms:

   a) Our own, which is a list of file-paths, weight delineated by a newline
      * Fast to load (loads text file of paths and weights directly into internal structures)
      * (Currently) Does not create a tree and so offers no to access to node-based navigation

   b) Standard lists of files, as per irfanView for example. These contain file-paths delineated by a newline, but no weighting
      * Fast to load (loads text file of fapths directly into internal structures, adds constant weight)
      * Offers no balancing; is effectively mode w1 by necessity
      * Does not create a tree and so offers no access to node-based navigation

3. .tree files
   * These are a serialised tree, as produced by enkan using Pickle
   * Fast to load (reads tree structure, calls calulate weights())
   * They contain all the possible information about the tree
   * Offers node-based navigation and full balancing control

### Issues combining each combination

#### .txt + .txt

.txt files can contain global information. At the moment we ignore global information in the second and subsequent .txt files.
We should try to harmonise the information in files, such that the initial global information remains relevant to later files.
What I mean by this is if the global setting in _file 1_ is [b4] and the global setting in _file 2_ is [b5] we graft the entries in _file 2_ such that their lowest-rung balance level is also [b4].
Duplicates should be handled gracefully, including being grafting aware so we don't duplicate a folder moved from it's original location in _file 1_ with the same folder in _file 2_

#### .tree + .tree

.tree's should be merged, with the _tree 1_ being the arbiter of truth when it comes to the __location__ of duplicates and _tree 2_ being the arbiter of truth when it comes to the __content__ of branches.

#### .tree + .txt

As per above, _tree 1_ should be the arbiter of truth when it comes to the __location__ of duplicates and __file 1__ should be the arbiter of truth when it comes to the __content__ of branches. This way, a large tree could be edited with, for example updated or additional files, by adding .tree + .txt.

#### .txt/.tree + .lst

Type (a) lists do not contain the full information to recreate a tree. We have a list of file paths/names and their weights. We could recreate a tree from the file paths, fill each end with files, add up each folders weights and pass them back up the tree, recreating everything except grafting.
Type (b) lists do not contain the full information to recreate a tree. We have a list of file paths/names. We could recreate a tree from the file paths and fill each end with files. If we are given a mode string, we could assign weights based on that.

Either of these could then be merged with an existing (or calculated) tree, paying attention to duplicates as before.

### Further Considerations

* This is related to the "(Re-)calculating Weight On The Fly" work done in the dev-user_proportion branch. We'll probably want to merge that into this step.
* Whatever we are loading, we should ensure we backfill as much information as we can infer
* More than two additions work from left to right (((a + b) + c) + d), etc.
* The order of truth for global mode is: command-line argument -> the first tree (PICKLE 3 records the original mode-string) -> the first .txt global mode modifier. We should recalculate weights to the right as required.
* Grafting to match a previous tree might drop files below the lowest_rung, where balancing makes no sense. We will need to handle that.
