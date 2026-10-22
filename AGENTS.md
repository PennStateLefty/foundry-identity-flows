# Contributor rules

- Follow PUBLICATION.md. Never commit real environment identifiers, endpoints, or authentication data.
- Keep tenant configuration and raw evidence exclusively under ignored `.local/` and `.azure/`.
- Use placeholders and aliases in documentation, examples, tests, and public output.
- Keep tokens out of model inputs, telemetry, exceptions, and persisted caches.
- Never turn a missing delegated token into an app-only retry.
- Preserve request-scoped context; never reuse call IDs across users or requests.
- Label results honestly: NOT RUN and BLOCKED are not PASS.
- Keep diagrams aligned with actual code and link authoritative sources.
- Read upstream licenses before copying code; preserve required notices.
- Do not run Azure deployments, directory mutations, consent grants, or cleanup without explicit operator approval.
