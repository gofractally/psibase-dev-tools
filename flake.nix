{
  description = "Psibase Package SDK (out-of-tree Rust packages) and DX tooling";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";

    fenix = {
      url = "github:nix-community/fenix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Fragile cargo tools, each pinned to the exact nixpkgs revision that
    # packages the required version (Rust 1.86.0 / psibase compatibility).
    # These deliberately do NOT follow nixpkgs.
    #   cargo-component 0.15.0
    nixpkgs-cargo-component.url = "github:NixOS/nixpkgs/b1e27a8646234340ea2c8b4e3f73e9e2b2bca505";
    #   cargo-generate 0.23.5, cargo-edit 0.13.7 (same nixpkgs rev)
    nixpkgs-cargo-generate.url = "github:NixOS/nixpkgs/1d0bb7b61b251a261b0963aacf4b141e770a4f1d";
    # Node: use pkgs.nodejs_24 from nixpkgs (nixos-26.05) — currently 24.22.3
    # (Nov 2026 CVE security release). No separate nixpkgs-nodejs pin.
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      fenix,
      nixpkgs-cargo-component,
      nixpkgs-cargo-generate,
    }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ] (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        # Standalone wasi-sdk 29 (matches psibase CMakeLists.txt default).
        wasiSdk = pkgs.stdenv.mkDerivation rec {
          pname = "wasi-sdk";
          version = "29";

          src = pkgs.fetchurl {
            url = "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-${version}/wasi-sdk-${version}.0-x86_64-linux.tar.gz";
            sha256 = "sha256-h9HRooedE5zcYkuWjvrT1Kl7gHjN/5XmOsiOyv0aAXE=";
          };

          nativeBuildInputs = [ pkgs.autoPatchelfHook ];
          buildInputs = [
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
          ];

          dontBuild = true;
          dontConfigure = true;

          installPhase = ''
            runHook preInstall
            mkdir -p $out
            cp -r * $out/
            runHook postInstall
          '';
        };

        psidk = pkgs.callPackage ./nix/sdk/package.nix { };
        sdkShell = import ./nix/sdk/shell.nix {
          inherit
            pkgs
            system
            fenix
            wasiSdk
            nixpkgs-cargo-component
            nixpkgs-cargo-generate
            psidk
            ;
          packageTemplates = ./nix/sdk/package-templates;
        };
      in
      {
        devShells = {
          default = sdkShell;
          sdk = sdkShell;
        };

        packages = {
          inherit psidk;
          wasi-sdk = wasiSdk;
          default = psidk;
        };
      }
    )
    // {
      templates = {
        package = {
          path = ./nix/sdk/template;
          description = "Standalone Rust psibase package workspace (packages/<app>)";
        };
        default = self.templates.package;
      };
    };
}
