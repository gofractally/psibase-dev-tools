# psibase-dev-tools

Extensions, AI rules, and other tooling that supports psibase development — kept out of the primary monorepo.

## Layout

| Path | Purpose |
|------|---------|
| [`extensions/vscode/`](extensions/vscode/) | **Psibase DX Tools** — extension for VS Code-compatible IDEs |

## Install Psibase DX Tools (local)

Not on the Marketplace.

```bash
cd extensions/vscode
npm install
npm run compile
```

Then in your IDE:

1. **Developer: Install Extension from Location...**
2. Select the `extensions/vscode` folder
3. Reload the window if the Extensions detail page still looks empty

Features, commands, and settings are documented in the extension README (also shown on the Extensions detail page after install):

**[extensions/vscode/README.md](extensions/vscode/README.md)**

## Developing the extension

```bash
cd extensions/vscode
npm install
npm run compile   # or: npm run watch
```

After code changes, reload the window (**Developer: Reload Window**) so the installed-from-location copy picks up `out/`.
