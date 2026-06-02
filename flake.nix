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
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python312
            uv
            postgresql
            chromium
            act
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
          ];

          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath (with pkgs; [
            stdenv.cc.cc.lib
            glib nss nspr dbus atk cups libdrm libxkbcommon pango cairo alsa-lib
          ]);

          shellHook = ''
            export CHROMIUM_EXECUTABLE_PATH="${pkgs.chromium}/bin/chromium"
            export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

            echo "Manga Tracker Architecture Loaded"
            echo "Environment: Python $(python3 --version | awk '{print $2}') | $(uv --version)"

            # Automatically sync the uv environment when entering the shell
            if [ -f "pyproject.toml" ]; then
              uv sync
            fi
          '';
        };
      }
    );
}
