import json

p1 = "/home/daytona/tgbot/vitrine/ferramentas/coleta_dados.py"
src = open(p1).read()

old_gm = '''def classifica_gemini(titulo: str) -> str:
    """Pede ao Gemini uma categoria curta quando as regras nao conhecem."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not titulo:
        return ""
    try:
        import requests as _rq
        r = _rq.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + key,
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    "Voce categoriza produtos de e-commerce. "
                                    "Responda APENAS com o nome de UMA categoria "
                                    "curta em português (1 a 3 palavras) para o "
                                    "produto abaixo. Nao explique.\\n"
                                    "Produto: " + titulo
                                )
                            }
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=30,
        )'''

new_gm = '''def classifica_gemini(titulo: str, cats_existentes=None) -> str:
    """Pede ao Gemini uma categoria curta quando as regras nao conhecem.
    Prefere reusar categorias ja existentes na vitrine."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not titulo:
        return ""
    try:
        import requests as _rq
        texto = (
            "Voce categoriza produtos de e-commerce. "
            "Responda APENAS com o nome de UMA categoria "
            "curta em português (1 a 3 palavras) para o "
            "produto abaixo. Nao explique.\\n"
            "Produto: " + titulo
        )
        if cats_existentes:
            texto += (
                "\\nPrefira UMA destas categorias ja existentes se "
                "fizer sentido: " + ", ".join(sorted(set(cats_existentes)))
            )
        r = _rq.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + key,
            json={
                "contents": [{"parts": [{"text": texto}]}],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=30,
        )'''
assert old_gm in src, "classifica_gemini nao encontrada"
src = src.replace(old_gm, new_gm, 1)

old_fin = '''def classifica_final(titulo: str) -> str:
    c = classifica_categoria(titulo)
    if c != "Outros":
        return c
    g = classifica_gemini(titulo)
    return g if g else "Outros"'''
new_fin = '''def classifica_final(titulo: str, cats_existentes=None) -> str:
    c = classifica_categoria(titulo)
    if c != "Outros":
        return c
    g = classifica_gemini(titulo, cats_existentes)
    return g if g else "Outros"'''
assert old_fin in src, "classifica_final nao encontrada"
src = src.replace(old_fin, new_fin, 1)

old_use = '''        if not r.get("categoria"):
            r["categoria"] = classifica_final(r.get("title", ""))'''
new_use = '''        if not r.get("categoria"):
            existentes = [
                x.get("categoria") for x in reg if x.get("categoria")
            ]
            r["categoria"] = classifica_final(
                r.get("title", ""), existentes
            )'''
assert old_use in src, "uso no rebuild ausente"
src = src.replace(old_use, new_use, 1)

open(p1, "w").write(src)
print("COLETA OK")
