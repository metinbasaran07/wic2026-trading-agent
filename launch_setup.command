#!/bin/bash
# Double-click this to open the Setup window

cd "$(dirname "$0")"

# Make sure we're in the right directory
python3 -c "
import sys
sys.path.insert(0, '.')
from setup_app import main
main()
"