#!/usr/bin/env python3
from pathlib import Path

from cirrus.plugins.docs import compiler


DOCS_DIR = Path(__file__).parent

if __name__ == '__main__':
    compiler
