"""Inbound token validation and delegated token acquisition."""

from contextvars import ContextVar
from functools import lru_cache
import os

USER_TOKEN: ContextVar[str] = ContextVar("user_token")
USER_CLAIMS: ContextVar[dict] = ContextVar("user_claims")

def workload_credential(*, asynchronous: bool = True):
    if asynchronous:
        from azure.identity import aio as identity
    else:
        import azure.identity as identity

    mode = os.environ.get("LAB_WORKLOAD_AUTH", "platform")
    if mode == "azure-cli":
        return identity.AzureCliCredential(tenant_id=os.environ["LAB_TENANT_ID"])
    if mode != "platform":
        raise ValueError("Unknown workload authentication mode.")
    if os.environ.get("AZURE_FEDERATED_TOKEN_FILE"):
        return identity.WorkloadIdentityCredential()
    return identity.ManagedIdentityCredential(client_id=os.environ.get("AZURE_CLIENT_ID"))


@lru_cache(maxsize=1)
def jwks():
    from jwt import PyJWKClient
    return PyJWKClient(
        f"https://login.microsoftonline.com/{os.environ['LAB_TENANT_ID']}/discovery/v2.0/keys",
        cache_keys=True,
    )


def validate(token: str) -> dict:
    import jwt
    tenant = os.environ["LAB_TENANT_ID"]
    claims = jwt.decode(
        token, jwks().get_signing_key_from_jwt(token).key,
        algorithms=["RS256"], audience=os.environ["LAB_API_CLIENT_ID"],
        issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
        options={"require": ["exp", "iat", "nbf", "aud", "iss", "tid", "oid"]},
    )
    if claims["tid"] != tenant or "access_as_user" not in claims.get("scp", "").split():
        raise jwt.InvalidTokenError("Required tenant or delegated scope missing.")
    return claims


def obo(assertion: str) -> str:
    import msal
    app = msal.ConfidentialClientApplication(
        os.environ["LAB_API_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{os.environ['LAB_TENANT_ID']}",
        client_credential=os.environ["LAB_API_CLIENT_SECRET"],
    )
    result = app.acquire_token_on_behalf_of(assertion, ["https://ai.azure.com/.default"])
    if "access_token" not in result:
        # Upstream error descriptions can contain tenant or object identifiers.
        raise PermissionError("Delegated token acquisition failed; check local consent and policy.")
    return result["access_token"]
