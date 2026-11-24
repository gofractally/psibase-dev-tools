# Package-dev SDK

Rust-oriented SDK for building psibase packages **without** cloning the psibase
monorepo and without a local `build/` tree. Lives in
[psibase-dev-tools](https://github.com/gofractally/psibase-dev-tools).

## Quick start (x86_64-linux)

```bash
mkdir my-apps && cd my-apps
nix flake init -t github:gofractally/psibase-dev-tools#package
# Local checkout of this repo:
#   nix flake lock --override-input psibase-dev-tools path:/path/to/psibase-dev-tools
# Local monorepo package template:
#   nix flake lock --override-input psibase path:/path/to/psibase
direnv allow   # or: nix develop

psiapp chain up 8090
psiapp new --destination . my-app
cd MyApp/ui && yarn && yarn build
cd .. && cargo-psibase package
cargo-psibase install -a http://psibase.localhost:8090/
psiapp chain down
```

From this repo directly:

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
- **New package:** `psiapp new [--destination DIR] [name]` → scaffolds a
  stand-alone Cargo workspace from the monorepo `package-templates/basic-01`
  pin (WIT for Host / Transact / Permissions is vendored in that template)

You do **not** get: C++/Boost/CMake native toolchain, mdbook, monorepo `build/` on `PATH`.

### Local chain (`psiapp chain`)

| | |
|--|--|
| Host | `psibase.localhost` (required for virtual hosting — not a bare IP) |
| Default API | `http://psibase.localhost:8080/` |
| State | `$XDG_STATE_HOME/psibase-devnet` (override with `PSIBASE_DEVNET_DIR`) |
| Boot | Runs `psibase boot` with the packaged set after `psinode` listens |

Keep **psibase CLI and chain on the same release** (SDK tooling with an
SDK-booted chain).

### New package (`psiapp new`)

Runs `cargo-generate` against the monorepo `package-templates/` flake input
into a user-chosen destination. Each package is its own Cargo workspace and
pins crates.io `psibase` / `psibase_macros` / `psibase_service`. UI is a
standalone Vite app using on-chain `@psibase/common-lib`.

## Flake template (`#package`)

`nix/sdk/template/` — consumer `flake.nix` / `.envrc` only. Create packages
with `psiapp new` after `nix develop`.

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
