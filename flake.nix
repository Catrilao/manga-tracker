{
  description = "Manga Tracker Pipeline Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        commonLibraries = with pkgs; [
          glib
          nss
          nspr
          dbus
          atk
          cups
          libdrm
          libxkbcommon
          pango
          cairo
          alsa-lib
          stdenv.cc.cc.lib
        ];

        commonPythonTools = with pkgs; [
          python312
          uv
          ruff
          mypy
          python312Packages.pytest
          python312Packages.pytest-playwright
          python312Packages.structlog
          python312Packages.requests
          python312Packages.greenlet
        ];

        mkEnv = extraInputs:
          pkgs.mkShell {
            buildInputs =
              commonPythonTools
              ++ commonLibraries
              ++ extraInputs;

            LD_LIBRARY_PATH =
              pkgs.lib.makeLibraryPath commonLibraries;

            shellHook = ''
              export CHROMIUM_EXECUTABLE_PATH="${pkgs.chromium}/bin/chromium"
              export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
              export UV_LINK_MODE=copy

              echo "Manga Tracker Environment"
              echo "Python $(python3 --version | awk '{print $2}')"
              echo "$(uv --version)"
            '';
          };
      in {
        devShells.default = mkEnv [
          pkgs.act
          pkgs.postgresql
          pkgs.chromium
        ];

        devShells.ci = mkEnv [
          pkgs.chromium
        ];
      });
}
