"""Client minimal pour OpenRouter (endpoint compatible OpenAI), utilisé par
score.py pour classifier le sentiment des mentions de pain au chocolat.

Pas de SDK OpenAI : un simple appel httpx suffit et évite une dépendance de
plus (cf. principe déjà appliqué à protocol.py)."""

import json
import re

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pac.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(RuntimeError):
    pass


class RetryableLLMError(LLMError):
    """Erreur transitoire (429/5xx) -- à retenter."""


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_markdown_fence(content: str) -> str:
    """Certains modèles (Claude via Bedrock/OpenRouter, observé en direct)
    enrobent leur réponse dans un bloc markdown ```json malgré
    `response_format: json_object` -- json.loads échoue sinon sur le "```"
    en tête. Repli sans effet si la réponse est déjà du JSON brut."""
    match = _FENCE_RE.match(content.strip())
    return match.group(1) if match else content


@retry(
    retry=retry_if_exception_type(RetryableLLMError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def classify_json(
    client: httpx.Client, system_prompt: str, user_prompt: str, model: str | None = None
) -> dict:
    """Appelle OpenRouter en mode JSON strict et renvoie l'objet décodé.

    Lève LLMError si la clé API est absente ou si la réponse n'est
    finalement pas un JSON valide après retries -- on ne devine jamais un
    résultat, on préfère faire échouer l'appelant pour cette mention.

    model : par défaut settings.openrouter_model (classification standard) ;
    verify_anomalies (score.py) passe settings.openrouter_verify_model pour
    un second avis avec un modèle plus capable.
    """
    if not settings.openrouter_api_key:
        raise LLMError(
            "OPENROUTER_API_KEY manquant (.env). Impossible de classifier les mentions."
        )

    resp = client.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=30,
    )

    if resp.status_code == 429 or resp.status_code >= 500:
        raise RetryableLLMError(f"OpenRouter {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
        return json.loads(_strip_markdown_fence(content))
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LLMError(f"Réponse OpenRouter non exploitable: {exc} -- {data}") from exc
