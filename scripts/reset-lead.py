#!/usr/bin/env python
from __future__ import annotations

import os
import sys

# Garante path correto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.reset_lead import main

if __name__ == "__main__":
    main()
