# enkan Configuration

enkan is moving toward one effective configuration source that combines built-in
defaults, `enkan.toml`, command-line options, input-file modifiers, and
session-only runtime changes.

The current `2.7.0.dev2` implementation is a first slice of that work. It
loads a TOML app config file, applies command-line overrides for migrated
settings, and exposes effective values through the internal `Config("item")`
interface. The migrated keys are defined in an internal registry that records
their TOML location, parser, default, CLI binding, and current scope.

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
random = false
dont_recurse = false
video = true
mute = true
navigation_basis = "folder"

[progress]
quiet = false

[cache]
background_preload = true
policy = "cache-all"
max_bytes = 104857600
```

Supported `navigation_basis` values:

- `folder`
- `branch`

Supported `cache.policy` values:

- `cache-all`
- `bounded-bytes`

Invalid values for known keys are treated as missing and fall back to the sane
built-in default. Unknown key names still raise an error, because they usually
mean a typo.

The legacy CLI flag `--no-background` maps to
`cache.background_preload = false`. The `--quiet` flag maps to
`progress.quiet = true`, which suppresses progress bars and progress toasts.

## Current Defaults

| Key | Built-in default |
| --- | --- |
| `slideshow.mode` | weighted mode, equivalent to internal `w1` behavior |
| `slideshow.random` | `false` |
| `slideshow.dont_recurse` | `false` |
| `slideshow.video` | `true` |
| `slideshow.mute` | `true` |
| `slideshow.navigation_basis` | `folder` |
| `progress.quiet` | `false` |
| `cache.background_preload` | `true` |
| `cache.policy` | `cache-all` |
| `cache.max_bytes` | `104857600` |

The package-level fallback file may set a different value during development.
It is useful for proving that `navigation_basis = "branch"` propagates into
slideshow startup without requiring a user config file.

## Precedence

The intended long-term precedence is:

1. Built-in defaults.
2. App config file.
3. Command-line options.
4. Input-file global modifiers.
5. Input-file local modifiers.
6. Session-only runtime changes.

Only the first three layers plus an internal runtime-override hook are wired for
migrated settings in `2.7.0.dev2`. Input-file modifier normalisation is planned
for the next slices.
