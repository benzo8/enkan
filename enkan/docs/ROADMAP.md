# Enkan Roadmap — v3 series

**Status:** planning/in-progress on `dev`  
**Audience:** public (high-level direction; not a personal TODO)

## Vision

v3 focuses on making Enkan more flexible (multiple input sources → one coherent tree), more interactive (live parameter tuning), smoother to use (first-class VLC controls and unified progress reporting), and more predictable via a clear configuration hierarchy.

---

## Scope (v3.x)

### InputProcessor

- [ ] **Multi-source inputs:** support combining multiple trees / lists / plain-text files into a single working tree.
- [ ] **Reverse-engineering:** infer a tree from list/txt inputs (with pluggable heuristics).
- [ ] **Conflict resolution:** deterministic merge when the same node appears in multiple sources (priority order + policy).
- [ ] **Serialization:** round-trip export/import (tree ⇄ list/txt) to make transformations reproducible.
- [ ] **Tests:** fixtures for mixed inputs; merge edge cases; round-trip stability.

### GUI

- [ ] **Live parameter updates:** change balancing/weights while running; reflect immediately in scheduling (no restart).
- [ ] **VLC controls:** play/pause/seek, rate, mute, full-screen; keyboard shortcuts; current time / duration display.
- [ ] **Progress UI:** progress bar in-GUI; status & currently playing; graceful error surfacing.

### Progress reporting (console + GUI)

- [ ] **tqdm adapter:** single progress “source” feeding both Tkinter and console concurrently.
- [ ] **Back-pressure aware updates:** throttled UI refresh; no event-loop starvation.
- [ ] **CLI flags:** `--no-console-progress` to silence console when running GUI; `--headless` for console-only.

### Config (MVP in v3.0)

- [ ] **Format:** Prefer **TOML** (stdlib `tomllib` on Py ≥3.11). YAML may be considered later.
- [ ] **Global config file:** e.g., `~/.config/enkan/config.toml` (Windows `%APPDATA%\Enkan\config.toml`).
- [ ] **Local config for trees:** a file alongside each `.txt`/`.tree` (same basename) auto-loads, e.g. `mylist.txt` + `mylist.toml`.
- [ ] **Inline modifiers (“in-line”):** key/value overrides embedded in `.txt`/definition files.
- [ ] **Precedence (lowest → highest):**  
      `global < local < CLI < global-in-line < local-in-line < in-app real-time`
- [ ] **Watchers:** local/global config hot-reload (debounced) where safe.
- [ ] **Validation:** typed schema; friendly errors + defaulting.
- [ ] **Persistence policy:** in-app real-time changes can be saved to a chosen scope (ask: local vs global) or discarded.

---

## Milestones & Acceptance Criteria

### v3.0.0 — Core refactor, config hierarchy & live controls

#### Goals

- Multi-source InputProcessor with reverse-engineering from lists.
- **Config system MVP with full precedence chain** and hot-reload for non-destructive params.
- Live parameter updates (balancing/weights) reflected mid-session.
- Minimal VLC transport (play/pause/seek) and a basic progress bar in the GUI.
- tqdm adapter proving simultaneous GUI + console progress.

#### Acceptance

- Given two lists and one tree, a single run produces a merged tree with documented, deterministic precedence.
- Changing balancing in the GUI immediately alters selection without restart.
- Play/pause/seek works on video; safe no-op on images.
- Console and GUI progress both update from one source (toggleable via flags).
- **Config:** global+local+inline+CLI precedence verified by tests; changing a local config file propagates without restart where applicable.
- Tests: merge, round-trip, live-update hooks, and config precedence pass in CI.

### v3.1.0 — UX polish & robustness

#### Goals

- Full VLC control surface (rate, mute, full-screen, scrubber with drag, keyboard shortcuts).
- Better error handling + non-blocking dialogs.
- Progress adapter hardened (no flicker, stable FPS).
- **Config presets:** save/load named parameter sets.

#### Acceptance

- End-to-end demo: load multiple sources → tweak presets live → video control surface behaves smoothly.
- Keyboard map documented in README; bindings tested on Windows & Linux.

### v3.2.0 — Performance & DX

#### Goals

- Caching/queues tuned for smoother transitions (no stutter while seeking).
- Structured logging; optional diagnostics for frame decode/render timing.
- Developer ergonomics: tighter CLI help, typed public API, docstrings.

#### Acceptance

- Measurable reduction in stutter on a sample set (document method).
- `--diagnostics` shows basic timing stats with minimal overhead.

---

## Breaking changes & migration

- **Input formats:** list/txt import gains structure conventions (indentation or `>` path separators). Provide a one-time converter.
- **Config keys:** parameters may move under a `params.*` namespace for live updates.
- **New files:** per-tree `*.toml` alongside definitions; global `config.toml` respected.
- Provide: `scripts/migrate_v2_to_v3.py` and examples in README.

---

## Design notes

- **Merge policy:** `(explicit tree > ordered list > plain txt)` by default; configurable via `--input-priority` or config.
- **Reverse-engineering:** heuristics module (`input_infer.py`) with strategies: indentation, delimiter, path-like lines.
- **Progress adapter:** facade producing events consumed by Tkinter and tqdm; avoids tight coupling between UI and console.
- **Config loader:** layered sources merged in order; immutable view per layer with explicit override set; hot-reload guarded by validators.

---

## Tracking

Use GitHub labels:

- `area:input`, `area:gui`, `area:playback`, `area:progress`, `area:config`,
  `type:refactor`, `type:feat`, `type:test`, `prio:P1/P2`.

Suggested epics:

- Epic: “InputProcessor v3 (multi-source + reverse)”
- Epic: “Live parameter updates”
- Epic: “VLC control surface”
- Epic: “Dual progress adapter (tqdm + Tk)”
- **Epic: “Config v3 (hierarchy + hot-reload)”**

---

## Out of scope (v3)

- New media types beyond images/video.
- Remote control features.
- Packaging/installers.

---

## Done when

- v3.0.0 ships with docs updated, migration notes, and a short demo GIF in the README.
- CI green across Windows & Linux; minimum Python version documented
