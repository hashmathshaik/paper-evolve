"""Contributor entry point. Python standard library only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from contribute import main

if __name__ == '__main__':
    main()
