# Package-dev SDK

Rust-oriented SDK for building psibase packages **without** cloning the psibase
monorepo and without a local `build/` tree. Lives in
[psibase-dev-tools](https://github.com/gofractally/psibase-dev-tools).

## Quick start (x86_64-linux)

```bash
mkdir my-apps && cd my-apps
nix flake init -t github:gofractally/psibase#package
# Until the template lands on main:
#   nix flake init -t github:gofractally/psibase/mm/nix-pkg-dev-prep#package
# Local bring-up of this SDK shell:
#   nix flake lock --override-input psibase-dev-tools path:/path/to/psibase-dev-tools
direnv allow   # or: nix develop

psiapp chain up 8090
psiapp new my-app
cd packages/MyApp/ui && yarn && yarn build
cd .. && cargo-psibase package
cargo-psibase install -a http://psibase.localhost:8090/
psiapp chain down
```

From this repo directly (SDK shell only — no workspace scaffold):

```bash
nix develop
```

## What the shell provides

- Prebuilt `psinode` / `psibase` / `psitest` from `packages.psidk`
- `cargo-psibase` from the Release tarball when present; otherwise **installed from
  crates.io** at `nix/release.nix` → `cargoPsibaseVersion`
- Rust 1.98 + wasm targets, cargo-component / cargo-generate / cargo-edit
- Node 24 (CVE-patched via nixos-26.05 `nodejs_24`) + Yarn, wasm-pack / wasm-tools / binaryen
- Flake `wasi-sdk`, mkcert, SoftHSM
- `PSIBASE_DATADIR` → store `share/psibase` (full package set from the tarball)
- **Local chain:** `psiapp chain up|down|status`
- **New app:** `psiapp new <name>` → scaffolds under `./packages`, then runs
  `wit-from-psidk` so Host / Transact / Permissions WIT are extracted from the
  same `$PSIBASE_DATADIR/packages/*.psi` that booted the chain

You do **not** get: C++/Boost/CMake native toolchain, mdbook, monorepo `build/` on `PATH`.

### WIT from the release tarball

Plugin interfaces are **not** committed under the template. `wit-from-psidk`
unzips `Host.psi` / `Transact.psi` / `Permissions.psi` from `PSIBASE_DATADIR`
and runs `wasm-tools component wit` on their plugin wasm, then writes
`plugin/wit/deps/*/world.wit` (plus conventional `world imports` stubs that
exist only in source WIT, not in the component). Bumping `nix/release.nix`
picks up matching interfaces automatically.

### Local chain (`psiapp chain`)

| | |
|--|--|
| Host | `psibase.localhost` (required for virtual hosting — not a bare IP) |
| Default API | `http://psibase.localhost:8080/` |
| State | `$XDG_STATE_HOME/psibase-devnet` (override with `PSIBASE_DEVNET_DIR`) |
| Boot | Runs `psibase boot` with the packaged set after `psinode` listens |

Keep **psibase CLI and chain on the same release** (SDK tooling with an
SDK-booted chain).

### New app (`psiapp new`)

Runs `cargo-generate` against [`package-templates/`](package-templates/) into
`./packages`, then `wit-from-psidk`. The template pins crates.io `psibase` /
`psibase_macros`. UI is a standalone Vite app using on-chain `@psibase/common-lib`.

## Flake template (`#package`)

Workspace scaffold lives in the **psibase monorepo** (`nix/sdk/template/`).
Instantiate with `nix flake init -t github:gofractally/psibase#package`. The
generated `flake.nix` pulls this repo’s Package SDK shell.

## Package artifact only

```bash
nix build .#psidk
./result/bin/psibase --version
```

Release pin: [`../release.nix`](../release.nix).

## Not this SDK

| Concern | Where |
|---------|--------|
| Contributor monorepo toolchain | psibase repo `nix develop` / `nix/dev/` |
| Thin node runtime / NixOS | psibase repo `packages.psibase` / `nix/deploy/` |
| Psibase DX Tools (VS Code / MCP) | [`extensions/vscode/`](../../extensions/vscode/) |
