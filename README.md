# psibase-dev-tools

Extensions, AI rules, and other tooling that supports psibase development — kept out of the primary monorepo.

## Layout

| Path | Purpose |
|------|---------|
| `extensions/psibase-package/` | VS Code / Cursor extension for psibase package naming |

## Psibase package naming extension

Diagnostics, hover help, inlay hints, rename, and correlated-name navigation for psibase package naming. Not published to the Marketplace.

One-time setup:

```bash
cd extensions/psibase-package
npm install
npm run compile
```

Then install with **Developer: Install Extension from Location...** and select `extensions/psibase-package`.

Optional workspace settings:

- `psibasePackage.inlayHints.enabled` (default `true`)
- `psibasePackage.statusBar.enabled` (default `true`)
- `psibasePackage.semanticHighlighting.enabled` (default `false`)
