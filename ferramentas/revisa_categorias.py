#!/usr/bin/env python3
"""IA revisa e consolida as categorias da vitrine.
Se estiver tudo certo, nao faz nada (sem commits inuteis)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "ferramentas"))

import coleta_dados as cd

reg = sorted(cd.carregar_registro(), key=lambda x: x["num"])
if not reg:
    print("vitrine vazia")
    sys.exit(0)

linhas = "\n".join(
    f"{r['num']} [{r.get('categoria', '(sem)')}] {r.get('title', '')}"
    for r in reg
)

prompt = (
    "Produtos atuais de uma vitrine online, no formato numero [categoria "
    "atual] titulo:\n\n"
    f"{linhas}\n\n"
    "Revise o agrupamento por categorias. Regras:\n"
    "- Use no maximo 6 categorias no total\n"
    "- Nomes curtos em portugues (1 a 3 palavras)\n"
    "- Produtos do mesmo tipo ficam JUNTOS (nao crie categoria com 1 "
    "produto se ela se encaixa numa existente)\n"
    "- Categorias com nome estranho ou generico demais devem ser trocadas\n"
    "- Todo produto mantem exatamente uma categoria\n\n"
    'Se o agrupamento atual ja estiver bom, responda exatamente:\n'
    '{"sem_mudancas": true}\n\n'
    "Senao, responda APENAS um objeto JSON com as mudancas necessarias "
    "(somente produtos que devem mudar de categoria):\n"
    '{"numero": "Nova Categoria"}'
)

key = os.getenv("GEMINI_API_KEY", "")
if not key:
    print("GEMINI_API_KEY ausente")
    sys.exit(0)

import requests as _rq
r = _rq.post(
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + key,
    json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    },
    timeout=60,
)
txt = (
    r.json()["candidates"][0]["content"]["parts"][0]["text"]
    .strip()
    .replace("```json", "")
    .replace("```", "")
    .strip()
)

try:
    mapa = json.loads(txt)
except Exception as e:
    print(f"resposta invalida da IA: {str(e)[:80]} | {txt[:120]}")
    sys.exit(0)

if mapa.get("sem_mudancas"):
    print("IA revisou: sem mudancas necessarias ✓")
    sys.exit(0)

mudaram = 0
for r in reg:
    nova = mapa.get(str(r["num"])) or mapa.get(r["num"])
    if nova and nova != r.get("categoria"):
        antiga = r.get("categoria", "")
        r["categoria"] = nova
        mudaram += 1
        print(f"#{r['num']:02d} {antiga} -> {nova} | {r['title'][:40]}")

if mudaram == 0:
    print("IA respondeu sem mudancas aplicaveis")
    sys.exit(0)

# limite de seguranca: maximo 6 categorias
cats = {r["categoria"] for r in reg}
if len(cats) > 6:
    print(f"IA sugeriu {len(cats)} categorias; acima do limite. Ignorando.")
    sys.exit(0)

cd.salvar_registro(reg)
cd.rebuild(reg)
print(f"concluido: {mudaram} produto(s) reclassificado(s)")
