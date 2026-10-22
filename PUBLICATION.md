# Publication policy

This repository is public. Treat every committed byte, commit message, issue,
workflow log, and pull request attachment as publicly readable.

## Never publish

- Real tenant, subscription, user, group, application, service-principal, or resource IDs.
- Real tenant-specific resource URLs, registry names, redirect URLs, email addresses, or account claims.
- Access tokens, refresh tokens, client secrets, certificates, private keys, token caches, or consent URLs.
- Raw responses, authentication errors, deployment output, traces, opaque call IDs, or identity hashes.
- Local filesystem paths or identity-bearing test screenshots.

Use `<tenant-id>`-style placeholders in templates and `user-a` / `user-b` aliases
in evidence. Do not replace placeholders with real values in tracked files.

Runtime inputs live in `.local/`; azd state lives in `.azure/`. Both are ignored.
Ignored files are not automatically safe: never force-add them, upload them as
artifacts, or print their contents in public CI. Directory mutation tools never
run automatically in CI.

Run `python scripts/check_public.py` against all tracked files before publishing.
After staging, run `python scripts/check_public.py --staged` to check exact index
contents, including newly staged files. The checks reject runtime files and
identifier-shaped strings.
It is a defense-in-depth heuristic, not a guarantee; manually inspect the staged
diff and use GitHub secret scanning where available.

Never auto-publish evidence. Review the generated allowlisted candidate, then
copy only that candidate into `results/`. A detected leak requires stopping
publication, revoking exposed credentials, and following incident procedures;
deleting the file in a later commit does not remove the exposure.
