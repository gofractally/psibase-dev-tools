# psibase-dev-tools

Extensions, AI/MCP tooling, and other helpers that support [psibase](https://github.com/gofractally/psibase) development — kept out of the primary monorepo.

## Layout

| Path                                       | Purpose                                                                  |
| ------------------------------------------ | ------------------------------------------------------------------------ |
| [`ai/tools/`](ai/tools/)                   | Portable Python package: build/test/chain tools + MCP stdio server       |
| [`extensions/vscode/`](extensions/vscode/) | **Psibase DX Tools** — package naming, Cursor AI rules, MCP registration |

## Install Psibase DX Tools (local)

Not required to keep this repo open after a Marketplace/VSIX install. For local development:

```bash
cd extensions/vscode
npm install
npm run compile
```

Then in your IDE:

1. **Developer: Install Extension from Location...**
2. Select the `extensions/vscode` folder
3. Reload the window if needed

Open a **psibase** workspace. The extension registers **`psibase-mcp`** (Cursor) and package-naming helpers only for that shape of repo.

Details: **[extensions/vscode/README.md](extensions/vscode/README.md)**

## AI tools package (developers)

```bash
cd ai/tools
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

`npm run compile` in the extension syncs `ai/tools` into `extensions/vscode/ai-tools` so Marketplace/local installs are self-contained.
