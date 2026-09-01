"""Conversational agent: grounds an LLM's answers in the live warehouse via
function calling, so every figure it states traces back to a real /data,
/projections or quality query rather than being recalled from model memory.
"""

import json
import logging

import duckdb
import openai
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..agent_tools import TOOL_SCHEMAS, execute_tool
from ..db import get_connection
from ..limiter import limiter
from ..llm import get_llm

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_MESSAGE_LENGTH = 2000
MAX_HISTORY_MESSAGES = 12

SYSTEM_PROMPT = """Tu es l'assistant IA d'OpenDataViz, l'observatoire des données \
qui suit 60 indicateurs (Économie, Santé, Éducation, Infrastructure) pour les 54 pays \
africains, de 2000 à 2024 (observé/imputé) puis 2025 à 2029 (projeté).

Règles impératives :
- Ne réponds JAMAIS un chiffre de mémoire : appelle toujours un outil pour le vérifier, \
même si tu penses le connaître.
- Précise systématiquement si une valeur est observée, imputée par Machine Learning \
(KNN/itérative), ou projetée (ElasticNet) — l'utilisateur doit toujours savoir à quel \
point une donnée est fiable.
- Si un outil renvoie une erreur ou aucune donnée, dis-le clairement plutôt que d'inventer.
- Réponds dans la langue du message de l'utilisateur.
- Sois concis et clair : privilégie des réponses courtes, avec les chiffres clés en avant \
(peu de texte d'habillage).
- Formatage strict : uniquement du texte, des **mots en gras** et des puces "- " pour les \
listes. N'utilise JAMAIS de titres Markdown (#, ##, ###), de listes numérotées, de tableaux, \
de séparateurs (---) ni d'émojis (y compris les drapeaux de pays) — l'interface de chat ne \
rend que ce sous-ensemble simple.
"""


class ChatMessage(BaseModel):
    role: str
    content: str = Field(max_length=MAX_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)


class ToolCallLog(BaseModel):
    name: str
    args: dict


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallLog] = []


def _friendly_llm_error(e: Exception) -> tuple[int, str]:
    """Maps common provider failures to a short, user-facing French message
    instead of surfacing the raw provider error body (which for rate limits
    in particular is a large, technical JSON blob)."""
    if isinstance(e, openai.RateLimitError):
        return 429, "Le fournisseur IA a atteint son quota (limite de requêtes gratuites atteinte). Réessaie plus tard, ou renseigne une clé avec un quota plus élevé dans .env."
    if isinstance(e, openai.AuthenticationError):
        return 401, "La clé API du fournisseur IA est invalide ou expirée. Vérifie GROQ_API_KEY / GEMINI_API_KEY dans .env."
    if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
        return 504, "Impossible de joindre le fournisseur IA (réseau ou délai dépassé). Réessaie dans un instant."
    return 502, "Le fournisseur IA a renvoyé une erreur inattendue. Réessaie, ou vérifie les logs de l'API pour le détail technique."


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
def chat(request: Request, req: ChatRequest, conn: duckdb.DuckDBPyConnection = Depends(get_connection)):
    client, model = get_llm()

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in req.history[-12:]]
    messages.append({"role": "user", "content": req.message})

    tool_log: list[ToolCallLog] = []

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("LLM call failed")
            status_code, detail = _friendly_llm_error(e)
            raise HTTPException(status_code=status_code, detail=detail)

        choice = completion.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            return ChatResponse(reply=msg.content or "", tool_calls=tool_log)

        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(tc.function.name, args, conn)
            tool_log.append(ToolCallLog(name=tc.function.name, args=args))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    return ChatResponse(
        reply="Désolé, je n'arrive pas à conclure sur cette question après plusieurs vérifications de données. Peux-tu la reformuler plus simplement ?",
        tool_calls=tool_log,
    )
