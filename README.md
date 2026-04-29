# enkan dev

A not-so-simple slideshow application for building rich, weighted photo and video playlists that you can drive with a lean Tkinter UI. enkan reads structured text input, builds a tree of sources, and serves images (and optional video) according to the weighting rules you specify.

Of course, enkan can show you images completely at random, but its real power comes as you delve deeper into weighting and grafting, giving you complete control over the balance of images you see.

For release history, see [CHANGELOG.md](CHANGELOG.md).

## Requirements

- Python ≥3.11
- Pillow
- python-vlc (for video support)
- matplotlib (for tree visualization)
- tqdm (progress bars)

Optional:

- customtkinter (enhanced GUI appearance)

## Installation

### From source

```bash
git clone -b dev https://github.com/benzo8/enkan.git
cd enkan
pip install -e .
```

If you install into a fresh environment, remember to install VLC separately so that `python-vlc` can find the native libraries.

## Features

- Weighted, fully random, sequential, folder-burst, and controlled-random image providers
- Tree-based directory organization with grafting
- Persistent viewing history, including across temporary scope changes
- Folder-aware subfolder and parent navigation modes
- EXIF orientation support
- Image caching and background preload for performance
- Video playback support (via VLC), including a bottom-reveal transport overlay
- Interactive GUI with zoom/pan
- Rotation persistence to EXIF

## Quick Start

1. Collect your image (and optional video) folders.
2. Create a text file (for example `shows/summer-show.txt`) that lists the folders you want to include. You can mix folders, individual files, nested `.txt` files, and inline weighting rules.
3. Launch enkan and point it at the file:

```bash
enkan --input_file shows/summer-show.txt --run
```

enkan will parse the file, build an in-memory tree, and open the slideshow window. Use the keyboard controls to navigate and switch providers. Add `--auto 8` to advance every eight seconds, or `--random` to start in completely random mode.

## Runtime Providers

enkan currently ships with five runtime image providers:

- `weighted` - the default weighted/balanced behavior, using the tree-derived image weights
- `random` - pure random selection, ignoring weights
- `sequential` - simple linear stepping through the current image set
- `burst` - weighted selection of a folder seed, then a short burst of images from that folder
- `controlled_random_weighted` (`CRW`) - a weighted provider with shared recency memory and streak penalties that reduces obvious streaks while still respecting the underlying weight model

### Controlled Random Weighted (CRW)

CRW is deliberately less statistically random than plain weighted selection so that it feels more random to a human viewer.

It keeps the existing image and tree weightings, but adds bucket-level memory:

- recently seen buckets are cooled off
- buckets that have not been seen for a while are gradually boosted
- repeated streaks from the same bucket are penalised

The result is usually a slideshow that feels less clumpy than pure weighted random, while still respecting the underlying weighting rules.

Internally, CRW now works from logical image-bearing tree nodes rather than rescanning every flattened image path when you switch into the provider. That keeps provider switching fast on large datasets, and it means a flattened node behaves as one shared memory unit rather than as many hidden filesystem folders.

By default, CRW groups images by the active balanced branch bucket rather than the immediate image-bearing node. That means sibling folders inside the same balanced branch can share recency memory when the tree structure says they belong to the same weighted bucket. If you are already running CRW, pressing `D` toggles between:

- `BB` - balanced-branch buckets
- `FB` - image-bearing node buckets

Use `Shift-D` to cycle the current provider status overlay. CRW currently supports `off`, `friendly`, `useful`, and `debug`.

## `.txt` Input Files

Text files let you describe complex shows declaratively. General rules:

- One path per non-empty line. Lines starting with `#` are comments.
- Windows paths can use `\\` or `/`. Surround a path with quotes if it contains spaces or commas.
- You can reference other `.txt`, `.lst`, or `.tree` files. enkan resolves them recursively.
- Place any number of square-bracket modifiers before the path to alter weighting, grouping, or behaviour.
- "Level" refers to the tree depth, which mirrors the folder depth (unless grafted), starting from root = 1

### Common Modifiers

| Syntax | Meaning |
| --- | --- |
| `[r]` | Set the entire show to run in fully random mode. |
| `[+]keyword` | Only include files whose path contains `keyword`. Repeat for multiple must-match terms. |
| `[-]keyword` | Exclude any path containing `keyword`. If you give an absolute file or folder, that path is skipped entirely. |
| `[NN%]` | Multiply a branch's weight by `NN%` relative to its siblings (e.g. `[150%]` gives that branch 1.5x the default share). |
| `[NN]` | For individual images, repeat the image `NN` times in the weighted pool. Useful for spotlighting a favourite shot. |
| `[%NN%]` | Reserve `NN%` of the parent branch's share for this node and divide the remainder among siblings. |
| `[bN]` | Switch the weighting mode at `level "N"` to balanced (`b`). Example: `[b2]` keeps siblings at level 2 evenly balanced. |
| `[wN[,slope]]` | Switch the weighting mode at `level "N"` to weighted (`w`), using descendant counts to apportion remaining percentage. Negative slopes favour smaller folders, positive slopes flatten toward balanced. |
| `[gN]` | Graft this branch up to tree level `N`, letting you bubble deep folders to a shallower menu. |
| `[>group-name]` | Assign the line to a named group so you can share grafting, proportion, or mode changes. Combine with a `*` line to define the group (see below). |
| `[f]` | Treat a directory as a flat bucket: gather every image under it into one node instead of mirroring the folder hierarchy. |
| `[v]` / `[nv]` | Force-enable or disable video for this branch (overrides the default or CLI flag). |
| `[m]` / `[nm]` | Force the slideshow to mute or unmute when media from this branch plays. |
| `[/]` | Do not recurse beyond this directory; only its direct files are considered. |

Modifiers can appear in any order so long as they precede the path, for example:

``` bash
[%40%][b3]D:\Media\Family Archive
[150%][v]E:\Clips\Action Cams
[>portraits][g3]F:\Photos\Portrait Sessions
```

### Global Defaults and Groups

Use a line whose path is just `*` to define global or group-level behaviour:

``` bash
[b1w2]*                                     # Balanced top level, weighted from level 2 downward
[v][nm]*                                    # Default to video enabled and audio unmuted
[>portraits][g3][%30%][w4,-20]*             # Define the "portraits" group once
[>portraits]F:\Photos\Portrait Sessions     # Apply the group to a folder
```

A group definition stores graft level, proportion, and mode modifiers. Any line tagged with the same `[>group]` inherits those settings.

### Nesting Other Files

- Pointing at another `.txt` file in a line imports everything from that file at the current position. (Only the Global Defaults from the top-level file are honoured.)
- `.lst` files are either:
  - plain CSV lines (`absolute\path\to\image.jpg,weight`). They are useful when you already have a hand-curated weighted list
  - new-line delimited lists of files (`absolute\path\to\image.jpg`), as produced by irfanView, et al
- `.tree` files are binary snapshots produced by `--outputtree`. enkan reuses them if the embedded version matches; for older trees it first attempts in-memory index repair and only falls back to the sibling `.txt` / `.lst` source if repair is not possible.

## CLI Reference

| Option | Purpose |
| --- | --- |
| `-i`, `--input_file` | One or more `.txt`, `.lst` or `.tree` files, or folder and/or file paths (including [modifiers] if desired) to process. |
| `--run` | Explicitly launch the slideshow (optional when you omit `--output*`). |
| `--outputlist [filename]` | Write a weighted `.lst` file instead of launching the GUI. |
| `--outputtree [filename]` | Persist the computed tree to a `.tree` file for fast reloads instead of lauching the GUI. |
| `--mode` | Provide a global mode string such as `b1w2` to override file defaults. |
| `--random` | Start in fully random mode (same as `[r]` in a file). |
| `--auto N` | Advance automatically every `N` seconds. |
| `--no-recurse` | Treat every supplied folder as non-recursive. |
| `--video` / `--no-video` | Force-enable or disable video globally. |
| `--no-mute` | Keep audio tracks unmuted (video default is muted). |
| `--no-background` | Run loaders in the foreground (useful when debugging). |
| `--test N` | Run `N` randomised draws and report the observed distribution. Combine with `--histo` for a matplotlib histogram. |
| `--test_model`, `--tm` | Comma-separated provider suffixes to compare during `--test`, for example `weighted,controlled_random_weighted`. |
| `--printtree` | Emit a text representation of the computed tree. |
| `--debug N` | Debug information: 2 INFO, 3 WARN, 4 DEBUG |
| `--testdepth`, `--histo`, `--debug` | Extra diagnostics for tuning your weighting setup. |

## Hotkeys (active during slideshow)

| Key | Function |
| --- | --- |
| Space | Next image |
| Left | Back through history |
| Right | Forward through history |
| Up | Next sequential image |
| Down | Previous sequential image |
| N | Toggle the information line |
| C | Select fully random provider |
| W | Select weighted/balanced provider |
| D | Select controlled-random weighted (`CRW`), or if CRW is already active toggle its bucket strategy (`BB` / `FB`) |
| Shift-D | Cycle the current provider status display (`CRW`: off / friendly / useful / debug) |
| L | Select linear / sequential provider |
| B | Select Folder Burst mode |
| Ctrl-B | Reset Folder Burst mode and force a new burst seed |
| S | Toggle Subfolder mode |
| T | Toggle Navigation mode between Branch and Folder |
| P | Follow branch/folder down into Parent Mode |
| O | Follow branch/folder up within Parent Mode |
| I | Step backwards through Parent Mode stack |
| U | Reset Parent Mode |
| Ctrl-D | Clear controlled-random selection memory for the current scope |
| M | Toggle mute |
| R | Rotate image clockwise by 90 degrees |
| Ctrl-R | Try to write current orientation to image EXIF data |
| Delete | Delete current image or video |
| Ctrl-Shift-M | Open the mode-adjust dialog |
| Ctrl-Shift-T | Print the current tree to the console |
| = / + / - | Zoom image |
| 0 | Reset Zoom |
| Shift-Cursor | Move viewport around zoomed image |
| A | Toggle Auto-Advance (Timed) Mode |

### Video Transport Overlay

When a video is playing, move the mouse near the bottom edge of the slideshow window to reveal the transport overlay. It shows playback progress, current time / duration, pause or resume, and click/drag seeking when VLC reports a known duration. The overlay hides automatically after a short idle period and is not shown for image slides.

## Navigation and Parent Mode

enkan can navigate in two modes:

- Branch - Parent Mode moves up and down the branches of the tree
- Folder - Parent Mode moves up and down the folder structure of the disk. If the folder you move to is not in the tree, enkan will need to read all the files below the current folder, whether they are in you input files or not. This can take a lot of time.

Subfolder mode and Parent mode temporarily restrict future selection to a smaller scope, but your viewer history is still preserved across those scope changes. If you explicitly go back, enkan can revisit images you saw before entering the temporary scope.

## Working With Lists and Trees

- Run `enkan -i show.txt --outputlist` to capture the fully expanded list (including virtual nodes and weights) into `show.lst`.
- Run `enkan -i show.txt --outputtree` to produce `show.tree`, a binary cache you can ship with a release for faster loading.
- Combine `--printtree` and `--test` while iterating on your `.txt` files to confirm that proportions and grafting behave the way you expect.
- Use `--tm weighted,controlled_random_weighted` with `--test` when you want to compare plain weighted behavior against CRW distribution on the same dataset.

## Tips

- Keep your `.txt` files in source control alongside the media curations—they capture the intent of the show far better than flat lists.
- Use groups to coordinate related folders (for example all portrait shoots) without repeating the same graft and mode modifiers on every line.
- When emphasising a single standout image, prefer an absolute modifier like `[25]` on the image line instead of inflating nearby branches.
- Large libraries benefit from building a `.tree` once and reusing it until the folder structure changes; enkan will try to repair older runtime indexes in memory before falling back to rebuilding from the sibling source file.

Have fun!
