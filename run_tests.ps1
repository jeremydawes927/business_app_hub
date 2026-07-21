$ErrorActionPreference = "Stop"
python -B -m unittest discover -s tests -p "test_*.py"
