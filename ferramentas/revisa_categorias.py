#!/usr/bin/env python3
"""IA organiza as categorias da vitrine.
Consolida produtos parecidos e cria categoria nova quando um produto
claramente nao se encaixa nas existentes. Se estiver tudo certo, nao faz
nada (sem commits inuteis). Erros de IA nunca derrubam o workflow."""
import hashlib
import json
import os
import re
import sys

import requests as rq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "ferramentas"))

import coleta_dados as cd

MAX_CATS = 8
CATS_INVALIDAS = {"outros", "diversos", "produto", "produtos", "item", "varios"}

_hf = os.path.join(ROOT, "ferramentas", ".last_review_hash")


def _hash_reg(reg):
    return hashlib.md5(
        json.dumps(sorted(reg, key=lambda x: x["num"]), sort_keys=True).encode()
    ).hexdigest()


def nome_ok(nome):
    n = (nome or "").strip().strip(".").title()
    if not 2 <= len(n) <= 32:
        return ""
    if n.lower() in CATS_INVALIDAS:
        return ""
    if not re.fullmatch(r"[A-Za-zÀ-ÿ0-9 &\-]+", n):
        return ""
    return n


def main():
    reg = sorted(cd.carregar_registro(), key=lambda x: x["num"])
    if not reg:
        print("vitrine vazia")
        return

    _hash_atual = _hash_reg(reg)
    if os.path.exists(_hf):
        _ultimo = open(_hf).read().strip()
        if _ultimo == _hash_atual:
            print("nada mudou desde a ultima revisao - skip ✓")
            return

    linhas = "\n".join(
        f"{r['num']} [{r.get('categoria', '(sem)')}] {r.get('title', '')}"
        for r in reg
    )
    cats_atuais = sorted({r.get("categoria", "") for r in reg if r.get("categoria")})

    prompt = (
        "Produtos de uma vitrine online, no formato numero [categoria atual] "
        "titulo:\n\n"
        f"{linhas}\n\n"
        "Categorias atuais: " + ", ".join(cats_atuais) + "\n\n"
        "Voce e o organizador de categorias desta vitrine. Tarefas:\n"
        "1. Consolide: produtos do mesmo tipo ficam JUNTOS na mesma categoria.\n"
        "2. CRIE uma categoria nova quando um produto claramente nao se "
        "encaixa em nenhuma existente (nem com ajuste de nome).\n"
        "3. Troque nomes genericos ou estranhos (ex: 'Outros', 'Diversos', "
        "'Item') por algo descritivo do grupo.\n\n"
        "Regras:\n"
        f"- Maximo {MAX_CATS} categorias no total\n"
        "- Nomes curtos em portugues (1 a 3 palavras), capitalizados\n"
        "- Nao crie categoria para UM produto se ele se encaixa bem numa "
        "existente\n"
        "- Todo produto mantem exatamente uma categoria\n\n"
        "Se o agrupamento ja estiver bom, responda exatamente:\n"
        '{"sem_mudancas": true}\n\n'
        "Senao, responda APENAS um objeto JSON com SOMENTE os produtos que "
        "devem mudar de categoria:\n"
        '{"numero": "Nova Categoria"}\n'
        "Exemplo: {\"7\": \"Pet Shop\", \"12\": \"Casa e Limpeza\"}"
    )

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY ausente - nada a fazer")
        return

    try:
        resp = rq.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + key,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=90,
        )
        txt = (
            resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            .strip()
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )
        m = re.search(r"\{.*\}", txt, re.S)
        mapa = json.loads(m.group(0) if m else txt)
    except Exception as e:
        print(f"IA indisponivel ou resposta invalida ({str(e)[:80]}) - mantenho tudo")
        return

    if not isinstance(mapa, dict) or mapa.get("sem_mudancas"):
        print("IA revisou: organizacao atual esta boa ✓")
        with open(_hf, "w") as f:
            f.write(_hash_atual)
        return

    mudaram = 0
    for r in reg:
        bruta = mapa.get(str(r["num"])) or mapa.get(r["num"])
        nova = nome_ok(bruta) if isinstance(bruta, str) else ""
        if not nova or nova == r.get("categoria"):
            continue
        antiga = r.get("categoria", "")
        r["categoria"] = nova
        mudaram += 1
        print(f"#{r['num']:02d} [{antiga}] -> [{nova}] | {r['title'][:40]}")

    cats_finais = {r["categoria"] for r in reg if r.get("categoria")}
    if len(cats_finais) > MAX_CATS:
        print(
            f"IA sugeriu {len(cats_finais)} categorias (limite {MAX_CATS}). "
            "Nada aplicado."
        )
        return

    if mudaram == 0:
        print("IA respondeu sem mudancas aplicaveis")
        with open(_hf, "w") as f:
            f.write(_hash_atual)
        return

    cd.salvar_registro(reg)
    mudou_pagina = cd.atualiza_categorias_pagina(reg)
    with open(_hf, "w") as f:
        f.write(_hash_reg(reg))
    print(
        f"concluido: {mudaram} reclassificado(s) | "
        f"{len(cats_finais)} categorias | "
        f"pagina {'atualizada (cirurgica)' if mudou_pagina else 'ja estava correta'}"
    )


try:
    main()
except Exception as e:
    print(f"erro nao critico na revisao: {str(e)[:120]}")
