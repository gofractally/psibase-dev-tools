# Psibase DX Tools

Development tools for [psibase](https://github.com/gofractally/psibase) in **VS Code-compatible IDEs**.

## Features

### Package naming

When a workspace contains `Cargo.toml`, the extension scans psibase packages and helps keep naming consistent across:

- `Cargo.toml` package / crate names
- `#[psibase::service(name = ...)]` (and related) attributes
- WIT `package` lines
- Related CMake / packaging metadata

You get:

- **Diagnostics** for naming constraint violations and mismatches
- **Hover** help describing the entity and correlated names
- **Inlay hints** labeling naming slots
- **Rename** across correlated occurrences
- **Find correlated names** from the command palette or status bar
- Optional **semantic highlighting** of naming identifiers

### AI rules (Cursor)

In **Cursor**, this extension can register AI rules for the agent (on by default). In other VS Code-compatible IDEs the settings appear but have no effect unless the host implements the same plugin API. Toggle them in [AI Rules settings](command:workbench.action.openSettings?%5B%22psibasePackage.aiRules%22%5D).

## Commands

| Command | Palette title |
|---------|----------------|
| `psibasePackage.renameEntity` | Psibase package: Rename entity… |
| `psibasePackage.findCorrelated` | Psibase package: Find correlated names |

## Settings

### Package naming

| Setting | Default | Description |
|---------|---------|-------------|
| `psibasePackage.inlayHints.enabled` | `true` | Inlay hints on naming slots |
| `psibasePackage.statusBar.enabled` | `true` | Package context on the status bar |
| `psibasePackage.semanticHighlighting.enabled` | `true` | Color naming identifiers by entity type |

Semantic highlighting also requires **Editor: Semantic Highlighting** (`editor.semanticHighlighting.enabled`) to be on. This extension sets that as a default when installed.

## Activation

Activates when the workspace contains a `Cargo.toml` (typical for psibase packages and the monorepo).
