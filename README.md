# psibase-dev-tools

Extensions, AI/MCP tooling, the Package SDK Nix environment, and other helpers
that support [psibase](https://github.com/gofractally/psibase) development —
kept out of the primary monorepo.

## Layout

| Path                                       | Purpose                                                                  |
| ------------------------------------------ | ------------------------------------------------------------------------ |
| [`ai/tools/`](ai/tools/)                   | Portable Python package: build/test/chain tools + MCP stdio server       |
| [`extensions/vscode/`](extensions/vscode/) | **Psibase DX Tools** — package naming, Cursor AI rules, MCP registration |
| [`nix/sdk/`](nix/sdk/)                     | **Package SDK** — `nix develop` for out-of-tree Rust packages             |

## Package SDK (x86_64-linux)

```bash
nix develop
# or scaffold a consumer workspace (template lives in the psibase monorepo):
#   nix flake init -t github:gofractally/psibase#package
```

Docs: **[nix/sdk/README.md](nix/sdk/README.md)**. Bump the released psidk pin in
[`nix/release.nix`](nix/release.nix) when moving to a new psibase release.

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
