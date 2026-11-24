set -euo pipefail

HOST="${PSIBASE_DEVNET_HOST:-psibase.localhost}"
PORT="${PSIBASE_DEVNET_PORT:-8080}"
PRODUCER="${PSIBASE_DEVNET_PRODUCER:-myprod}"
ADMIN_IP="${PSIBASE_ADMIN_IP:-${HOST_IP:-127.0.0.1}}"
STATE_DIR="${PSIBASE_DEVNET_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/psibase-devnet}"

usage() {
  cat <<EOF
Usage: psiapp <command> …

Commands:
  chain up [port] [producer] [state-dir]   Start fresh chain, boot, print API URL
  chain down                               Stop the chain started by up
  chain status                             Show pid / API if running
  new [--destination DIR] [--version VER] [name]   Scaffold a stand-alone package

Environment (chain):
  PSIBASE_DEVNET_HOST / PORT / PRODUCER / DIR
  PSIBASE_ADMIN_IP / HOST_IP

API URL uses a hostname (not a bare IP) for virtual hosting.
EOF
}

api_url() { echo "http://${HOST}:${PORT}/"; }

wait_http() {
  local n code
  for n in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 \
      -H "Host: x-admin.${HOST}" "http://127.0.0.1:${PORT}/" 2>/dev/null || echo 000)
    if [[ "$code" =~ ^[0-9]+$ ]] && [[ "$code" != "000" ]]; then
      return 0
    fi
    sleep 0.25
  done
  echo "error: psinode did not accept HTTP on port ${PORT}" >&2
  return 1
}

chain_up() {
  PORT="${1:-$PORT}"
  PRODUCER="${2:-$PRODUCER}"
  STATE_DIR="${3:-$STATE_DIR}"
  mkdir -p "$STATE_DIR"
  local pidfile="$STATE_DIR/psinode.pid"
  local logfile="$STATE_DIR/psinode.log"
  local dbdir="$STATE_DIR/db"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "error: psinode already running (pid $(cat "$pidfile")). Run: psiapp chain down" >&2
    exit 1
  fi
  rm -rf "$dbdir"
  mkdir -p "$dbdir"
  echo "Starting psinode (host=${HOST} port=${PORT} producer=${PRODUCER})"
  echo "  state: $STATE_DIR"
  PSIBASE_ADMIN_IP="$ADMIN_IP" \
    psinode "$dbdir" -p "$PRODUCER" -l "$PORT" --host "$HOST" \
    >"$logfile" 2>&1 &
  echo $! >"$pidfile"
  wait_http
  echo "Booting chain…"
  psibase boot -a "$(api_url)" -p "$PRODUCER"
  echo ""
  echo "Devnet ready."
  echo "  API:      $(api_url)"
  echo "  Admin:    http://x-admin.${HOST}:${PORT}/"
  echo "  Producer: ${PRODUCER}"
  echo "  Stop:     psiapp chain down"
  echo ""
  echo "  cargo-psibase install -a $(api_url)"
}

chain_down() {
  local pidfile="$STATE_DIR/psinode.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "No pid file at $pidfile (nothing to stop)."
    return 0
  fi
  local pid
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -9 "$pid" 2>/dev/null || true
    echo "Stopped psinode (pid $pid)."
  else
    echo "Stale pid file (process $pid not running)."
  fi
  rm -f "$pidfile"
}

chain_status() {
  local pidfile="$STATE_DIR/psinode.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "running pid=$(cat "$pidfile") api=$(api_url) state=$STATE_DIR"
  else
    echo "stopped state=$STATE_DIR"
    return 1
  fi
}

cmd_chain() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    up) chain_up "$@" ;;
    down) chain_down "$@" ;;
    status) chain_status "$@" ;;
    -h|--help|help|"")
      cat <<EOF
Usage: psiapp chain <up|down|status> …

  up [port] [producer] [state-dir]   Start fresh chain, boot, print API URL
  down                               Stop the chain started by up
  status                             Show pid / API if running
EOF
      ;;
    *)
      echo "unknown chain subcommand: $sub" >&2
      echo "Try: psiapp chain --help" >&2
      exit 1
      ;;
  esac
}

read_rust_workspace_version() {
  local cargo_toml="$1"
  sed -n '/^\[workspace.package\]/,/^\[/{s/^version = "\([^"]*\)"/\1/p}' "$cargo_toml" | head -1
}

cmd_new() {
  local TEMPLATES="${PSIBASE_PACKAGE_TEMPLATES:-}"
  if [[ -z "$TEMPLATES" || ! -d "$TEMPLATES" ]]; then
    echo "error: PSIBASE_PACKAGE_TEMPLATES not set (enter nix develop)" >&2
    exit 1
  fi

  local DEST=""
  local NAME=""
  local VERSION=""
  local PASSTHRU=()
  local SILENT=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --destination|-d)
        DEST="${2:-}"
        shift 2
        ;;
      --name|-n)
        NAME="${2:-}"
        shift 2
        ;;
      --version)
        VERSION="${2:-}"
        shift 2
        ;;
      --silent|-s)
        SILENT=1
        PASSTHRU+=("$1")
        shift
        ;;
      -h|--help)
        cat <<EOF
Usage: psiapp new [--destination DIR] [--name NAME] [--version VER] [project-name]

Scaffolds a stand-alone package (own Cargo workspace) from the monorepo
package-templates/basic-01 pin. WIT deps ship with the template.

Destination, name, and version are prompted when omitted. Version defaults
to rust/Cargo.toml [workspace.package] from the psibase flake input.
EOF
        return 0
        ;;
      *)
        if [[ -z "$NAME" && "$1" != -* ]]; then
          NAME="$1"
        else
          PASSTHRU+=("$1")
        fi
        shift
        ;;
    esac
  done

  # Same tree as the template pin: <psibase>/rust/Cargo.toml
  local DEFAULT_VERSION=""
  local RUST_CARGO
  RUST_CARGO="$(dirname "$TEMPLATES")/rust/Cargo.toml"
  if [[ -f "$RUST_CARGO" ]]; then
    DEFAULT_VERSION="$(read_rust_workspace_version "$RUST_CARGO")"
  fi
  if [[ -z "$DEFAULT_VERSION" ]]; then
    DEFAULT_VERSION="${PSIBASE_CRATE_VERSION:-@psibaseCrateVersion@}"
  fi

  if [[ -z "$DEST" ]]; then
    if [[ "$SILENT" -eq 1 ]]; then
      echo "error: --destination is required with --silent" >&2
      exit 1
    fi
    read -r -p "Destination directory (parent of the new package): " DEST
  fi
  if [[ -z "$DEST" ]]; then
    echo "error: destination is required" >&2
    exit 1
  fi
  mkdir -p "$DEST"
  DEST="$(cd "$DEST" && pwd)"

  if [[ -z "$NAME" ]]; then
    if [[ "$SILENT" -eq 1 ]]; then
      echo "error: --name is required with --silent" >&2
      exit 1
    fi
    read -r -p "Package name (≤8 lowercase kebab-case): " NAME
  fi
  if [[ -z "$NAME" ]]; then
    echo "error: package name is required" >&2
    exit 1
  fi

  if [[ -z "$VERSION" ]]; then
    if [[ "$SILENT" -eq 1 ]]; then
      VERSION="$DEFAULT_VERSION"
    else
      read -r -p "Psibase version [$DEFAULT_VERSION]: " VERSION
      VERSION="${VERSION:-$DEFAULT_VERSION}"
    fi
  fi

  local TEMPLATE_SRC="$TEMPLATES/basic-01"
  if [[ ! -d "$TEMPLATE_SRC" ]]; then
    echo "error: missing template at $TEMPLATE_SRC" >&2
    exit 1
  fi
  # Flake copies live in the Nix store (mode 0444). cargo-generate copies
  # those modes into its work dir then fails with EACCES when rewriting files.
  # Not `local`: EXIT trap must still see WORK after cmd_new returns/fails.
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/psiapp-new.XXXXXX")"
  trap 'rm -rf "$WORK"' EXIT
  cp -a "$TEMPLATE_SRC" "$WORK/template"
  chmod -R u+w "$WORK/template"

  local CAMEL
  CAMEL="$(echo "$NAME" | sed -E 's/(^|-)([a-z])/\U\2/g')"
  # Binary is `cargo-generate` with a `generate` subcommand; cargo subcommand is
  # `cargo generate` (same flags).
  if command -v cargo >/dev/null 2>&1 && cargo generate --help >/dev/null 2>&1; then
    GENERATE=(cargo generate)
  elif command -v cargo-generate >/dev/null 2>&1; then
    GENERATE=(cargo-generate generate)
  else
    echo "error: cargo-generate not found" >&2
    exit 1
  fi

  if [[ -e "$DEST/$CAMEL" ]]; then
    echo "error: $DEST/$CAMEL already exists" >&2
    exit 1
  fi

  # Stage into a nested temp dir: cargo-generate inspects destination/Cargo.toml
  # and fails on virtual workspaces.
  STAGE="$(mktemp -d "$WORK/stage.XXXXXX")"
  echo "Generating '$NAME' into $DEST/$CAMEL (psibase $VERSION, crates.io)…"
  "${GENERATE[@]}" \
    --path "$WORK/template" \
    --destination "$STAGE" \
    --init \
    -v \
    --allow-commands \
    --name "$NAME" \
    --define "version=$VERSION" \
    --define "description=${PSIBASE_NEW_DESCRIPTION:-An example application}" \
    --define "psibase_rust_root=" \
    "${PASSTHRU[@]}"

  if [[ ! -d "$STAGE/$CAMEL" ]]; then
    echo "error: expected $STAGE/$CAMEL after generate" >&2
    exit 1
  fi
  mv "$STAGE/$CAMEL" "$DEST/"

  echo ""
  echo "Next:"
  echo "  cd $DEST/$CAMEL/ui && yarn && yarn build"
  echo "  cd $DEST/$CAMEL && cargo-psibase package"
}

cmd="${1:-}"
shift || true
case "$cmd" in
  chain) cmd_chain "$@" ;;
  new) cmd_new "$@" ;;
  -h|--help|help|"") usage ;;
  *)
    echo "unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
