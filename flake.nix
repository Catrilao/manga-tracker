{
  description = "Manga Tracker Pipeline Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        commonTools = with pkgs; [
          prettier
          python312
          uv
          supabase-cli
        ];

        mkEnv = extraInputs:
          pkgs.mkShell {
            buildInputs =
              commonTools
              ++ extraInputs;

            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];

            shellHook = ''
              export CHROMIUM_EXECUTABLE_PATH="${pkgs.chromium}/bin/chromium"
              export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
              export UV_LINK_MODE=copy
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
