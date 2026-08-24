#!/usr/bin/env python3
"""Wrapper: gera a pagina via gera_pagina.py."""
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ferramentas"))

ok = runpy.run_path(os.path.join(ROOT, "ferramentas", "gera_pagina.py"))["gerar"]()
sys.exit(0 if ok else 1)
