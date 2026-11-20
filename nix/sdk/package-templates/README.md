# SDK package templates (`cargo-generate`)

Out-of-tree app scaffold for `nix develop` / `psiapp new`.

- Pins crates.io `psibase` / `psibase_macros` (see workspace `Cargo.toml`)
- Does **not** vendor Host / Transact / Permissions WIT — `psiapp new` runs
  `wit-from-psidk` to extract them from `$PSIBASE_DATADIR/packages/*.psi`
- Ships a standalone Vite UI (runtime `@psibase/common-lib` from the chain)

## Usage

From an SDK workspace root (directory that contains `packages/Cargo.toml`):

```bash
psiapp new my-app
# or:
cargo generate -p "$PSIBASE_PACKAGE_TEMPLATES/sdk-basic-01" --destination ./packages --init \
  -v --allow-commands --name my-app --define version=0.29.0
wit-from-psidk ./packages/MyApp/plugin/wit/deps
```

Then:

```bash
cd packages/MyApp/ui && yarn && yarn build
cd .. && cargo-psibase package
cargo-psibase install -a http://psibase.localhost:8090/
```
