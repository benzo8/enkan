# enkan Configuration

enkan is moving toward one effective configuration source that combines built-in
defaults, `enkan.toml`, command-line options, and input-file modifiers. Runtime
UI state is seeded from config but remains owned by the runtime component that
changes it.

The current `2.7.0.dev2` implementation is a first slice of that work. It
loads a TOML app config file, applies command-line overrides for migrated
settings, and exposes effective values through fully qualified internal lookups
such as `Config("slideshow.navigation_basis")`. The migrated keys are defined
in an internal registry that records their TOML location, parser, default, CLI
binding, and current scope.

## Config File Discovery

When `--config` is not supplied, enkan searches for `enkan.toml` in this order.
The first file found wins; files are not merged.

1. The current working directory.
2. `%APPDATA%\enkan\enkan.toml` on Windows, or
   `~/.config/enkan/enkan.toml` when `APPDATA` is unset.
3. The enkan package folder, used for bundled fallback defaults.

When `--config PATH` is supplied, that path is used directly. If the explicit
path does not exist, startup fails.

## Current Keys

```toml
[slideshow]
mode = "b1"
provider = "weighted"
video = true
mute = true
navigation_basis = "folder"
interval = 10000
auto = false

[progress]
quiet = false

[cache]
background_preload = true
policy = "cache-all"
max_bytes = 104857600
preload_queue_length = 3
cache_size = 10
history_queue_length = 25
```

Supported `navigation_basis` values:

- `folder`
- `branch`

Supported `slideshow.provider` values:

- `weighted`
- `controlled_random_weighted` (`CRW` is accepted as an alias in config and CLI)
- `burst`
- `random`

Supported `cache.policy` values:

- `cache-all`
- `bounded-bytes`

Invalid values for known keys are treated as missing and fall back to the sane
built-in default. Unknown key names still raise an error, because they usually
mean a typo.

Registry-backed command-line flags now use the same validation as TOML values.
For example, `--navigation-basis branch` and `--nb branch` map to
`slideshow.navigation_basis = "branch"`. `--provider burst` maps to
`slideshow.provider = "burst"`, `--provider CRW` maps to
`slideshow.provider = "controlled_random_weighted"`, and the legacy `--random`
flag maps to `slideshow.provider = "random"`. `--interval 7500` sets
`slideshow.interval = 7500` without starting auto-advance, `--auto` starts
auto-advance with the configured interval, and `--auto 7500` does both. The
legacy negative flag
`--no-background` and alias `--nbg` map to the positive key
`cache.background_preload = false`; `--background-preload` maps it to `true`.
The `--quiet` flag maps to `progress.quiet = true`, which suppresses progress
bars and progress toasts.
`slideshow.video` is a runtime filter: `video = false` or `--no-video` prevents
videos from being selected for playback, but does not remove videos while
building `.txt` inputs. Use `[v]` / `[nv]` in `.txt` files for build-time video
inclusion.

## Current Defaults

| Key | Built-in default |
| --- | --- |
| `slideshow.mode` | weighted mode, equivalent to internal `w1` behavior |
| `slideshow.provider` | `weighted` |
| `slideshow.video` | `true` |
| `slideshow.mute` | `true` |
| `slideshow.navigation_basis` | `folder` |
| `slideshow.interval` | `10000` |
| `slideshow.auto` | `false` |
| `progress.quiet` | `false` |
| `cache.background_preload` | `true` |
| `cache.policy` | `cache-all` |
| `cache.max_bytes` | `104857600` |
| `cache.preload_queue_length` | `3` |
| `cache.cache_size` | `10` |
| `cache.history_queue_length` | `25` |

The package-level fallback file may set a different value during development.
It is useful for proving that `navigation_basis = "branch"` propagates into
slideshow startup without requiring a user config file.

## Precedence

The effective precedence is:

1. Built-in defaults.
2. App config file.
3. Input-file global modifiers.
4. Input-file local modifiers.
5. Command-line options.
6. Session-only runtime changes.

Command-line options are the highest persisted/user-supplied layer. They are
intended for case-by-case overrides, so TOML config and input-file modifiers
must not silently beat an explicit CLI argument. Input-file modifiers remain
build-scoped; they only participate in this ordering where they express the
same setting as a registry-backed option.

For `slideshow.mode`, a tree snapshot records the final effective build mode.
Loading a `.tree` without `--mode` uses that recorded mode; loading it with
`--mode` applies the CLI mode instead.
