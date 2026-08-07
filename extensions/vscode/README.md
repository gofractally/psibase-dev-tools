# Psibase DX Tools

Development tools for [psibase](https://github.com/gofractally/psibase) in **VS Code-compatible IDEs** (Cursor recommended for AI/MCP features).

After install (Marketplace or local), the extension **does not depend** on a `psibase-dev-tools` checkout. Features arm only when the open workspace looks like the psibase monorepo (`packages/Cargo.toml` + root `CMakeLists.txt` with `project(psibase)`).

## Features

### Package naming

Scans psibase packages and helps keep naming consistent across:

- `Cargo.toml` package / crate names
- `#[psibase::service(name = ...)]` (and related) attributes
- WIT `package` lines
- Related CMake / packaging metadata

You get diagnostics, hover, inlay hints, rename, find-correlated, and optional semantic highlighting.

### AI rules (Cursor)

Registers contributor/dev AI rules for the agent while a psibase workspace is open. Optional rules are toggleable under [AI Rules settings](command:workbench.action.openSettings?%5B%22psibasePackage.aiRules%22%5D). The **prefer psibase-mcp** rule is always on (no toggle).

If the psibase monorepo still has `.cursor/rules/ai-tools-mcp-tools.mdc`, remove that file after installing this extension so the guidance is not applied twice.

### MCP server (Cursor)

Registers **`psibase-mcp`**: build / test / local-chain tools (`start_full_build`, `start_service_tests`, `launch_chain`, …).

- Always on in a psibase workspace (no settings toggle).
- The extension creates and owns a Python venv (global storage) and installs the bundled `ai-tools` package on first activate / extension upgrade.
- Job state is stored per workspace.
- Unrelated hand-installed MCP entries (e.g. a separate ai-tools checkout) are left alone.

## Commands

| Command                         | Palette title                          |
| ------------------------------- | -------------------------------------- |
| `psibasePackage.renameEntity`   | Psibase package: Rename entity…        |
| `psibasePackage.findCorrelated` | Psibase package: Find correlated names |

## Settings

### Package naming

| Setting                                       | Default | Description                             |
| --------------------------------------------- | ------- | --------------------------------------- |
| `psibasePackage.inlayHints.enabled`           | `true`  | Inlay hints on naming slots             |
| `psibasePackage.statusBar.enabled`            | `true`  | Package context on the status bar       |
| `psibasePackage.semanticHighlighting.enabled` | `true`  | Color naming identifiers by entity type |

## Activation

Activates when the workspace contains `packages/Cargo.toml`. Package helpers, AI rules, and MCP registration run only for folders that match the psibase monorepo shape.

## Local install (from this repo)

```bash
cd extensions/vscode
npm install
npm run compile   # syncs ../../ai/tools into ./ai-tools, then tsc
```

Then **Developer: Install Extension from Location...** → select `extensions/vscode`.
