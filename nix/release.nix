# Pin for the published Ubuntu psidk tarball used by packages.psidk /
# the Package SDK shell. Bump `crateVersion` (and `srcHash`) when moving
# trains; `version` / URL follow from it. Prefetch hash:
#   nix store prefetch-file --hash-type sha256 \
#     https://github.com/gofractally/psibase/releases/download/vVERSION/psidk-ubuntu-2404.tar.gz
let
  # crates.io train (no -pre).
  crateVersion = "0.29.0";
  # Release tag / tarball train (may carry -pre while crates.io does not).
  version = "${crateVersion}-pre";
in
{
  inherit version;
  cargoPsibaseVersion = crateVersion;
  psibaseCrateVersion = crateVersion;
  # Download URL for that release’s psidk tarball (`${version}` in the path).
  # When bumping the train, re-prefetch and replace `srcHash` for the new URL.
  srcUrl = "https://github.com/gofractally/psibase/releases/download/v${version}/psidk-ubuntu-2404.tar.gz";
  srcHash = "sha256-1r4nLq5GquMosZbM6f2zzWa8M7efkNSuypDaN4vQVfU=";
  sourceRoot = "psidk-ubuntu-2404";
}
