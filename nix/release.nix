# Pin for the published Ubuntu psidk tarball used by packages.psidk /
# the Package SDK shell. Bump version + srcHash together:
#   nix store prefetch-file --hash-type sha256 \
#     https://github.com/gofractally/psibase/releases/download/vVERSION/psidk-ubuntu-2404.tar.gz
#
# Held at 0.23: 0.24 production boot fails (verify-sig) in the psibase
# monorepo deploy tests. Keep cargoPsibaseVersion / psibaseCrateVersion
# aligned with the release train (crates.io has no -pre suffix).
{
  version = "0.23.0-pre";
  cargoPsibaseVersion = "0.23.0";
  psibaseCrateVersion = "0.23.0";
  srcUrl = "https://github.com/gofractally/psibase/releases/download/v0.23.0-pre/psidk-ubuntu-2404.tar.gz";
  srcHash = "sha256-l9bdB9RKz9FQLiBnXaQsHNoveOTMt1r5xRghLTfqKsQ=";
  sourceRoot = "psidk-ubuntu-2404";
}
