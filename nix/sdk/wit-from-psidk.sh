# Materialize Host / Transact / Permissions WIT for cargo-component from the
# same psidk package set that supplies psinode/psibase (PSIBASE_DATADIR).
#
# Usage: wit-from-psidk <dest-wit-deps-dir>
# Example: wit-from-psidk packages/MyApp/plugin/wit/deps
# Sourced into a writeShellApplication body (no shebang).

DEST="${1:-}"
if [[ -z "$DEST" ]]; then
  echo "Usage: wit-from-psidk <dest-wit-deps-dir>" >&2
  exit 1
fi

DATADIR="${PSIBASE_DATADIR:-}"
if [[ -z "$DATADIR" || ! -d "$DATADIR/packages" ]]; then
  echo "error: PSIBASE_DATADIR/packages not set or missing (enter the Package SDK nix shell)" >&2
  exit 1
fi

if ! command -v wasm-tools >/dev/null 2>&1; then
  echo "error: wasm-tools not on PATH" >&2
  exit 1
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo "error: unzip not on PATH" >&2
  exit 1
fi

PACKAGES="$DATADIR/packages"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/wit-from-psidk.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

extract_psi() {
  local name="$1"
  local psi="$PACKAGES/${name}.psi"
  if [[ ! -f "$psi" ]]; then
    echo "error: missing $psi" >&2
    exit 1
  fi
  mkdir -p "$WORK/$name"
  unzip -qo -d "$WORK/$name" "$psi"
}

# Append conventional `world imports` (and friends) used by app scaffolds.
# Component-extracted WIT has interfaces only; include worlds live in source.
append_worlds() {
  local file="$1"
  local kind="$2"
  case "$kind" in
    host-common)
      cat >>"$file" <<'EOF'

world imports {
    import server;
    import client;
}

world privileged {
    import admin;
}
EOF
      ;;
    transact)
      cat >>"$file" <<'EOF'

world imports {
    import intf;
    import auth;
    import network;
    import admin;
}
EOF
      ;;
    permissions)
      cat >>"$file" <<'EOF'

world imports {
    import api;
    import types;
}
EOF
      ;;
  esac
}

write_pkg() {
  local src="$1"
  local dest_dir="$2"
  local worlds="$3"
  if [[ ! -f "$src" ]]; then
    echo "error: expected extracted WIT at $src" >&2
    exit 1
  fi
  mkdir -p "$dest_dir"
  cp "$src" "$dest_dir/world.wit"
  if [[ -n "$worlds" ]]; then
    append_worlds "$dest_dir/world.wit" "$worlds"
  fi
}

echo "Extracting WIT from $PACKAGES (psidk package set)…"

extract_psi Host
extract_psi Transact
extract_psi Permissions

HOST_TYPES_WASM="$WORK/Host/data/host/types.wasm"
HOST_COMMON_WASM="$WORK/Host/data/host/common.wasm"
TRANSACT_WASM="$WORK/Transact/data/transact/plugin.wasm"
PERMISSIONS_WASM="$WORK/Permissions/data/permissions/plugin.wasm"

for f in "$HOST_TYPES_WASM" "$HOST_COMMON_WASM" "$TRANSACT_WASM" "$PERMISSIONS_WASM"; do
  if [[ ! -f "$f" ]]; then
    echo "error: missing plugin wasm in package: $f" >&2
    exit 1
  fi
done

mkdir -p "$WORK/out/host-types" "$WORK/out/host-common" "$WORK/out/transact" "$WORK/out/permissions"
wasm-tools component wit --out-dir "$WORK/out/host-types" "$HOST_TYPES_WASM" >/dev/null
wasm-tools component wit --out-dir "$WORK/out/host-common" "$HOST_COMMON_WASM" >/dev/null
wasm-tools component wit --out-dir "$WORK/out/transact" "$TRANSACT_WASM" >/dev/null
wasm-tools component wit --out-dir "$WORK/out/permissions" "$PERMISSIONS_WASM" >/dev/null

rm -rf "$DEST"
mkdir -p "$DEST"

# Prefer the exporting package's own interface document from each component.
write_pkg "$WORK/out/host-types/deps/types.wit" "$DEST/host-types" ""
write_pkg "$WORK/out/host-common/deps/common.wit" "$DEST/host-common" "host-common"
write_pkg "$WORK/out/transact/deps/transact:plugin.wit" "$DEST/transact" "transact"
write_pkg "$WORK/out/permissions/deps/permissions:plugin.wit" "$DEST/permissions" "permissions"

# Empty impl.wit stubs were historically next to world.wit for some deps;
# cargo-component path deps point at world.wit only. No nested source deps.

echo "Wrote WIT deps under $DEST"
ls -la "$DEST"/*/world.wit
