# psibase-dev-tools

Extensions, AI rules, and other tooling that supports psibase development — kept out of the primary monorepo.

## Layout

| Path | Purpose |
|------|---------|
| `extensions/psibase-package/` | VS Code / Cursor extension for package naming + AI rules |

## Psibase package naming extension

Diagnostics, hover help, inlay hints, rename, and correlated-name navigation for psibase package naming. Also registers Cursor AI rules via the extension API (no writes into `.cursor/rules/`). Not published to the Marketplace.

One-time setup:

```bash
cd extensions/psibase-package
npm install
npm run compile
```

Then install with **Developer: Install Extension from Location...** and select `extensions/psibase-package`.

### Package naming settings

- `psibasePackage.inlayHints.enabled` (default `true`)
- `psibasePackage.statusBar.enabled` (default `true`)
- `psibasePackage.semanticHighlighting.enabled` (default `true`)

### AI Rules settings

All default `true`. Toggle under the extension settings categories:

**AI Rules: Contributors**

- `psibasePackage.aiRules.contributors.noBackwardCompatibility`
- `psibasePackage.aiRules.contributors.noWritableGit`
- `psibasePackage.aiRules.contributors.packageBackendSharedTypes`

**AI Rules: Devs**

- `psibasePackage.aiRules.devs.serviceActionFailures`

Rule text lives in `extensions/psibase-package/cursor-plugins/<rule-id>/`. In Cursor, enabled rules are registered with `vscode.cursor.plugins.registerPath`; disabled rules are unregistered. No-ops in plain VS Code.
