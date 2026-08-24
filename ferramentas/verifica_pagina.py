#!/usr/bin/env python3
"""Verifica integridade da pagina e reconstrói automaticamente se houver erro."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

P = "index.html"
html = open(P, encoding="utf-8").read() if os.path.exists(P) else ""
sem_com = re.sub(r"<!--.*?-->", "", html, flags=re.S)
abertas = len(re.findall(r"<div\b", sem_com))
fechadas = sem_com.count("</div>")

problemas = []
if abertas != fechadas:
    problemas.append(f"divs desbalanceadas ({abertas}/{fechadas})")
if "<script" not in html:
    problemas.append("sem javascript")
if "aplicarFiltros" not in html:
    problemas.append("funcao de filtro ausente")
if 'id="catMenu"' not in html:
    problemas.append("menu de categorias ausente")
if 'id="searchInput"' not in html:
    problemas.append("barra de busca ausente")
if "</html>" not in html or "<footer" not in html.lower():
    problemas.append("final da pagina truncado")
for m in re.finditer(r'src="(img/[^"]+)"', html):
    if not os.path.exists(m.group(1)):
        problemas.append(f"imagem faltando: {m.group(1)}")

if not problemas:
    print("pagina integra ✓ (nenhum problema)")
    sys.exit(0)

print("PROBLEMAS DETECTADOS:", "; ".join(problemas))
print("reconstruindo pagina...")
r = subprocess.run(
    [sys.executable, os.path.join(ROOT, "ferramentas", "gera_pagina.py")],
    capture_output=True,
    text=True,
)
print(r.stdout[-500:])
if r.returncode != 0:
    print(r.stderr[-300:])
    sys.exit(1)

# confere de novo
html2 = open(P, encoding="utf-8").read()
ok = (
    "<script" in html2
    and "aplicarFiltros" in html2
    and 'id="catMenu"' in html2
    and "</html>" in html2
)
print("pagina reparada ✓" if ok else "FALHOU ao reparar!")
sys.exit(0 if ok else 1)
