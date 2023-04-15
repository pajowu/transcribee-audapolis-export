let
  # We use a fixed version of nixpkgs here, so we get a recent enough version of
  # rustc for automerge-py
  pkgs = import
    (fetchTarball {
      name = "nixpkgs-unstable-new-enough-pdm";
      url = "https://github.com/NixOS/nixpkgs/archive/43862987c3cf2554a542c6dd81f5f37435eb1423.tar.gz";
    })
    { };

in
pkgs.mkShell {
  buildInputs = with pkgs; [
    pre-commit

    python310
    python310Packages.black
    poetry

    # for automerge-py
    libiconv
    rustc
    cargo
  ];

}
