"""Audience-specific outbound authentication and request context transport."""

from urllib.parse import urlparse

FOUNDRY_SCOPE = "https://ai.azure.com/.default"
CALL_ID = "x-agent-foundry-call-id"


def require_https(url: str, *, local: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("Configured endpoint cannot contain credentials, query, or fragment.")
    if parsed.scheme == "https" and parsed.hostname:
        return url.rstrip("/")
    if local and parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return url.rstrip("/")
    raise ValueError("An HTTPS endpoint is required.")


def responses_url(project: str, agent: str) -> str:
    if not agent or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in agent):
        raise ValueError("Invalid agent name.")
    return f"{require_https(project)}/agents/{agent}/endpoint/protocols/openai/responses?api-version=v1"


def context_headers(call_id: str | None, *, forward: bool = True) -> dict[str, str]:
    return {CALL_ID: call_id} if forward and call_id else {}


async def invoke(url: str, token: str, headers: dict[str, str], text: str) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        response = await client.post(
            url,
            headers={**headers, "Authorization": f"Bearer {token}"},
            json={"input": text, "stream": False, "store": False, "background": False},
        )
        response.raise_for_status()
        body = response.json()
    if body.get("status") != "completed":
        raise RuntimeError("Foundry response did not complete.")
    return body
