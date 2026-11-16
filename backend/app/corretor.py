"""Botão "Corrigir meu texto": ortografia e pontuação pelo LanguageTool (serviço grátis).

O texto vai para api.languagetool.org (servidor na Alemanha), que devolve as sugestões; aqui
aplicamos só as seguras (ortografia, gramática, pontuação, espaços) e devolvemos o texto pronto.
Limite do serviço grátis: 20 correções por minuto para o servidor todo.
"""

import re

import httpx

from .config import settings

# Tipos de sugestão aplicados. Fora: estilo, redundância, regionalismos (mudam o jeito de escrever).
CATEGORIAS = {"TYPOS", "GRAMMAR", "PUNCTUATION", "TYPOGRAPHY", "CASING", "CONFUSED_WORDS"}
# Maiúscula no começo da frase é feita aqui: a regra do LanguageTool esconde o erro de ortografia
# da mesma palavra ("amanha" → só sugeria "Amanha").
REGRAS_DESLIGADAS = "UPPERCASE_SENTENCE_START"
MAX_CARACTERES = 5000


class CorretorError(Exception):
    pass


def _sem_espacos(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _aceita(m: dict, original: str) -> str | None:
    """A troca sugerida, se for segura. `original` é o trecho marcado no texto."""
    regra = m.get("rule") or {}
    categoria = (regra.get("category") or {}).get("id")
    trocas = [r.get("value") for r in (m.get("replacements") or []) if r.get("value") is not None]
    if categoria not in CATEGORIAS or not trocas:
        return None
    troca = trocas[0]
    if troca == original:
        return None
    if categoria == "TYPOGRAPHY" and _sem_espacos(troca) != _sem_espacos(original):
        return None  # tipografia: só mexe em espaços (ex.: "boleto ," → "boleto,"), nunca em letras/emojis
    if regra.get("id", "").startswith("MORFOLOGIK") and (re.search(r"[A-Z0-9]", original) or "@" in original):
        return None  # palavra com maiúscula/número: nome próprio, sigla, código — não "corrige"
    return troca


def aplicar(texto: str, matches: list[dict]) -> tuple[str, list[dict]]:
    """Aplica as sugestões aceitas. As posições do LanguageTool contam em UTF-16 (emoji = 2)."""
    u16 = texto.encode("utf-16-le")
    trocas = []
    fim_anterior = -1
    for m in sorted(matches, key=lambda x: (x.get("offset", 0), x.get("length", 0))):
        ini, tam = int(m.get("offset", 0)), int(m.get("length", 0))
        if ini < fim_anterior or tam <= 0 or (ini + tam) * 2 > len(u16):
            continue  # sobreposta ou fora do texto
        original = u16[ini * 2:(ini + tam) * 2].decode("utf-16-le", errors="strict")
        troca = _aceita(m, original)
        if troca is None:
            continue
        trocas.append((ini, tam, original, troca, m.get("message") or ""))
        fim_anterior = ini + tam
    for ini, tam, _o, troca, _msg in reversed(trocas):
        u16 = u16[: ini * 2] + troca.encode("utf-16-le") + u16[(ini + tam) * 2:]
    feitas = [{"from": o, "to": t, "why": msg} for _i, _t, o, t, msg in trocas]
    return u16.decode("utf-16-le"), feitas


_INICIO_DE_FRASE = re.compile(r"(^|[.!?]\s+|\n\s*)([a-zà-öø-ÿ])")


def maiuscula_no_inicio(texto: str) -> tuple[str, int]:
    """Primeira letra do texto e de cada frase (depois de . ! ? ou de uma linha nova) em maiúscula."""
    n = 0

    def troca(m):
        nonlocal n
        n += 1
        return m.group(1) + m.group(2).upper()

    return _INICIO_DE_FRASE.sub(troca, texto), n


async def corrigir(texto: str, client: httpx.AsyncClient | None = None) -> dict:
    texto = texto or ""
    if not texto.strip():
        return {"text": texto, "corrections": 0, "items": []}
    if len(texto) > MAX_CARACTERES:
        raise CorretorError(f"Texto grande demais para corrigir (máximo {MAX_CARACTERES} caracteres)")
    dados = {"text": texto, "language": "pt-BR", "disabledRules": REGRAS_DESLIGADAS}
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=12) as c:
                r = await c.post(settings.languagetool_url, data=dados)
        else:
            r = await client.post(settings.languagetool_url, data=dados)
    except httpx.HTTPError as e:
        raise CorretorError("O corretor (LanguageTool) não respondeu. Tente de novo.") from e
    if r.status_code == 429:
        raise CorretorError("Muitas correções neste minuto (limite do corretor grátis). Espere um pouco e tente de novo.")
    if r.status_code != 200:
        raise CorretorError(f"O corretor (LanguageTool) recusou o texto ({r.status_code}).")
    try:
        matches = r.json().get("matches") or []
    except ValueError as e:
        raise CorretorError("Resposta estranha do corretor (LanguageTool).") from e
    corrigido, feitas = aplicar(texto, matches)
    corrigido, maiusculas = maiuscula_no_inicio(corrigido)
    return {"text": corrigido, "corrections": len(feitas) + maiusculas, "items": feitas}
