# Psibase package SDK consumer

Scaffolded with:

```bash
nix flake init -t github:gofractally/psibase-dev-tools#package
direnv allow   # or: nix develop
```

## Layout

```text
.
├── flake.nix / .envrc   # Package SDK shell from this flake
└── <App>/               # from `psiapp new` (stand-alone Cargo workspace)
```

## Develop

```bash
direnv allow   # or: nix develop
psiapp chain up 8090  # avoid ports already in use (e.g. 8080)

psiapp new --destination . my-app
cd MyApp/ui && yarn && yarn build
cd .. && cargo-psibase package
cargo-psibase install -a http://psibase.localhost:8090/

psiapp chain down
```

Use the SDK shell’s `psibase` (same release as the chain). A monorepo `build/`
`psibase` from a newer train will mis-encode account names on an SDK-booted chain.

Each package’s `Cargo.lock` (after the first `cargo` / `cargo-psibase` run)
should be committed so Cargo does not pull crates that need a newer rustc than
the SDK pin.
