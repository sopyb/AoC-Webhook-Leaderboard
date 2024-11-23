{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    poetry
    # Additional build dependencies that might be needed
    # gcc
    # pkg-config
  ];

  shellHook = ''
    # Create virtual environment if it doesn't exist
    if [ ! -d .venv ]; then
      echo "Creating virtual environment..."
      poetry config virtualenvs.in-project true
      poetry install
    fi

    # Activate virtual environment
    source .venv/bin/activate

    # Show installed poetry version
    echo "Poetry version: $(poetry --version)"

    # Show python version
    echo "Python version: $(python --version)"
  '';
}