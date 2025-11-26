# enkan

A not-so-simple slideshow application for building rich, weighted photo and video playlists that you can drive with a lean Tkinter UI. enkan reads structured text input, builds a tree of sources, and serves images (and optional video) according to the weighting rules you specify.

Of course, enkan can show you images completely at random, but its real power comes as you delve deeper into weighting and grafting, giving you complete control over the balance of images you see.

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
git clone https://github.com/yourusername/enkan.git
cd enkan
pip install -e .
```

If you install into a fresh environment, remember to install VLC separately so that `python-vlc` can find the native libraries.

## Features

- Weighted and balanced image selection modes
- Tree-based directory organization with grafting
- EXIF orientation support
- Image caching for performance
- Video playback support (via VLC)
- Interactive GUI with zoom/pan
- Rotation persistence to EXIF

## Quick Start

1. Collect your image (and optional video) folders.
2. Create a text file (for example `shows/summer-show.txt`) that lists the folders you want to include. You can mix folders, individual files, nested `.txt` files, and inline weighting rules.
3. Launch enkan and point it at the file:

```bash
enkan --input_file shows/summer-show.txt --run
```

enkan will parse the file, build an in-memory tree, and open the slideshow window. Use the keyboard or on-screen controls to navigate. Add `--auto 8` to advance every eight seconds, or `--random` to drop into completely random mode.

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
- `.tree` files are binary snapshots produced by `--outputtree`. enkan reuses them if the embedded version matches; otherwise it falls back to the sibling `.txt` / `.lst` source.

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
| `--ignore-below-bottom` | Ignore files in folders below lowest balance level. |
| `--video` / `--no-video` | Force-enable or disable video globally. |
| `--no-mute` | Keep audio tracks unmuted (video default is muted). |
| `--no-background` | Run loaders in the foreground (useful when debugging). |
| `--test N` | Run `N` randomised draws and report the observed distribution. Combine with `--histo` for a matplotlib histogram. |
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
| N | Toggle information line |
| C | Toggle Random Mode - overrides weightings |
| S | Toggle Slideshow Mode - limit slideshow to subfolder containing current image |
| N | Toggle Navigation Mode - switch between Branch and Folder. See below for details on Navigation Mode and Parent Mode|
| P | Enter Parent Mode - move up tree and limit slideshow to images in folders below current parent |
| I | Step backwards through Parent Mode (if possible) |
| U | Reset Parent Mode |
| W | Select Weighted/Balanced mode |
| B | Select Folder Burst Mode - pick 5 images from the current folder, then randomly select the next folder and repeat |
| L | Select Liner / Sequential Mode |
| Ctrl-B | Reset Folder Burst Mode - pick a new folder and begin Folder Burst mode again |
| R | Rotate image clockwise by 90 degrees |
| Ctrl-R | Try to write current orientation to image EXIF data |
| = / + / - | Zoom image |
| 0 | Reset Zoom |
| Shift-Cursor | Move viewport around zoomed image |
| A | Toggle Auto-Advance (Timed) Mode |

## Navigation and Parent Mode

enkan can navigate in two modes:

- Branch - Parent Mode moves up and down the branches of the tree
- Folder - Parent Mode moves up and down the folder structure of the disk. If the folder you move to is not in the tree, enkan will need to read all the files below the current folder, whether they are in you input files or not. This can take a lot of time.

## Working With Lists and Trees

- Run `enkan -i show.txt --outputlist` to capture the fully expanded list (including virtual nodes and weights) into `show.lst`.
- Run `enkan -i show.txt --outputtree` to produce `show.tree`, a binary cache you can ship with a release for faster loading.
- Combine `--printtree` and `--test` while iterating on your `.txt` files to confirm that proportions and grafting behave the way you expect.

## Tips

- Keep your `.txt` files in source control alongside the media curations—they capture the intent of the show far better than flat lists.
- Use groups to coordinate related folders (for example all portrait shoots) without repeating the same graft and mode modifiers on every line.
- When emphasising a single standout image, prefer an absolute modifier like `[25]` on the image line instead of inflating nearby branches.
- Large libraries benefit from building a `.tree` once and reusing it until the folder structure changes; enkan automatically regenerates it if the pickle version does not match.

Have fun!
