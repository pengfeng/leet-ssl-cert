---
name: leet-ssl-cert-create
description: Issue an SSL/TLS certificate with leet-ssl-cert. Use when the user asks to create, issue, request, or renew a certificate for one or more domains. The only required input from the user is the domain name; everything else is loaded from .env defaults or sensible presets.
---

# leet-ssl-cert: create a certificate

Issue (or renew) a certificate via the `leet-ssl-cert` CLI in this repo. This skill wraps `leet-ssl-cert issue`. It does **not** deploy — use the `leet-ssl-cert-deploy` skill for that.

## When to use

The user says things like "create a cert for example.com", "issue a certificate", "renew the cert for foo.com", "I need an SSL cert".

## Required input

- `domain` — one FQDN, or several space/comma-separated. The first domain becomes the cert's primary; the rest become SANs.

## Optional inputs (skill arguments)

If the user passes any of these explicitly, use them. Otherwise resolve from defaults below. Never ask the user for any of these unless resolution failed.

| Field | Notes |
|---|---|
| `name` | Cert name in the config. Default = slug of apex domain (`example.com` → `example-com`). |
| `email` | ACME account email. |
| `dns_provider` | `aliyun` \| `aws` \| `gcp` \| `godaddy`. |
| `directory_url` | ACME directory. Default = Let's Encrypt prod. Switch to staging only if user says "staging" / "test". |
| `key_size` | Default 2048. |
| `renewal_days` | Default 30. |
| `dry_run` | Pass `--dry-run` to the CLI. |
| `force` | Pass `--force` to the CLI. |

## Defaults resolution order

The CLI auto-loads `./.env` and `~/.leet-ssl-cert/.env` at startup (existing process env vars always win). For each unspecified field, walk these in order and stop at the first hit:

1. Skill argument from the invocation.
2. Process env / `.env` keys (see table below).
3. Existing `leet-ssl-cert.yaml` (cwd, then `~/.leet-ssl-cert/config.yaml`). Reuse `account.email`, `acme.*`, and — only if an existing cert's apex domain matches the new domain's apex — its `dns_provider`.
4. `.leet/.init-inputs.json` cache (written by `leet-ssl-cert init`) — for `email` only. Do **not** infer `dns_provider` from this cache; the init defaults reflect the first cert ever set up, not the new domain.
5. Hardcoded fallbacks: `directory_url=https://acme-v02.api.letsencrypt.org/directory`, `key_size=2048`, `renewal_days=30`.

If after step 5 a required field is still missing (`email` or `dns_provider`), ask the user *once* with `AskUserQuestion`, then **persist the answer back to `./.env`** (preserving existing keys) so future runs don't ask again.

**Always confirm `dns_provider` with the user before issuing**, unless it was passed as an explicit skill argument or set via `LEET_SSL_CERT_DNS_PROVIDER` in env/`.env`. DNS zone ownership is per-domain and can't be reliably inferred from other certs in the config — guessing wrong wastes an ACME round-trip and surfaces a confusing "Unable to find DNS zone" error. Use `AskUserQuestion` with options `aliyun` / `aws` / `gcp` / `godaddy` (preselect the resolved value if any). This confirmation can be folded into the same prompt as the final Proceed/Cancel preview in step 8.

### `.env` keys read by this skill

| Key | Meaning |
|---|---|
| `LEET_SSL_CERT_EMAIL` | ACME account email. |
| `LEET_SSL_CERT_DNS_PROVIDER` | Default DNS provider. |
| `LEET_SSL_CERT_DIRECTORY_URL` | ACME directory URL. |
| `LEET_SSL_CERT_KEY_SIZE` | RSA key size. |
| `LEET_SSL_CERT_RENEWAL_DAYS` | Renewal threshold in days. |
| `LEET_SSL_CERT_NAME` | Default cert name. |

Provider creds are kept under their conventional names (next section).

## Credential check

After `dns_provider` is known, verify the matching env vars are populated (the CLI's `.env` autoloader will already have run, so `.env` values count). Do **not** call `gcloud`, `aws`, `aliyun`, or any cloud CLI — only consult env vars and files in the repo.

| `dns_provider` | Required env vars |
|---|---|
| `aliyun` | `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_ACCESS_KEY_SECRET` |
| `aws` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (or `AWS_DEFAULT_REGION`) |
| `gcp` | `GOOGLE_APPLICATION_CREDENTIALS` (path to JSON key) **and** `GOOGLE_CLOUD_PROJECT` |
| `godaddy` | `GODADDY_API_KEY`, `GODADDY_API_SECRET` |

If any are missing, **stop** and print the exact `export …` lines plus a pointer to the relevant guide in [docs/](../../docs/). Do not proceed.

## Steps

1. **Locate the source config.** Prefer `./leet-ssl-cert.yaml`. If absent, fall back to `~/.leet-ssl-cert/config.yaml`. If neither exists, you'll be creating a fresh config from scratch.
2. **Verify the CLI is installed**: `leet-ssl-cert --help`. If not, tell the user to `pip install -e '.[<dns_provider>]'` from the repo root and stop.
3. **Resolve all fields** using the order above.
4. **Verify creds** per the table.
5. **Build the cert entry** in memory:
   ```yaml
   - name: <name>
     domains:
       - <domain1>
       - <domain2>
     dns_provider: <dns_provider>
   ```
   No `deploy:` block — that's the deploy skill's job.
6. **Compose the new config.** Start from the source config (if any), then merge in:
   - Make sure `account.email`, `acme.*`, and `providers.<dns_provider>` exist; add them with env-var references (`${ALIBABA_CLOUD_ACCESS_KEY_ID}`, etc.) following [config/example.yaml](../../config/example.yaml).
   - If `certificates:` already has an entry with the same `name`, replace its `domains` and `dns_provider` (keep its `deploy:` if present). Otherwise append.
7. **Write to a NEW timestamped sibling file** — never modify the source config in place. Filename: `leet-ssl-cert.<YYYYMMDD-HHMMSS>.yaml` in the same directory as the source (or cwd if no source exists). Use `date +%Y%m%d-%H%M%S` for the timestamp.
8. **Preview.** Show:
   - A compact summary (name, domains, dns_provider, email, directory_url, dry_run/force).
   - The path to the new config file.
   - The diff vs. the source config (use `diff -u` if both exist).
   - Single `AskUserQuestion` with options "Proceed" / "Cancel".
9. **Run** the CLI against the new file:
   ```bash
   leet-ssl-cert --config <new-file> issue --name <name> [--dry-run] [--force]
   ```
10. **Report** the cert path under `~/.leet-ssl-cert/certs/<name>/`, the expiry from CLI output, and the path of the timestamped config used. Tell the user they can promote it (`mv leet-ssl-cert.<ts>.yaml leet-ssl-cert.yaml`) if they're happy with it. Suggest the deploy skill as a follow-up.
11. **Persist defaults to `./.env`.** For any `LEET_SSL_CERT_*` value just resolved or collected (especially `LEET_SSL_CERT_EMAIL`, `LEET_SSL_CERT_DNS_PROVIDER`, `LEET_SSL_CERT_NAME`), append to or update `./.env` so the next run picks them up. Do not write secrets there unless the user explicitly asked.

## Don'ts

- Don't run any cloud-vendor CLI (`gcloud`, `aws`, `aliyun`). Only the `leet-ssl-cert` CLI from this repo.
- Don't collect secrets via prompts. Tell the user to `export` them (or add to `.env`) and stop.
- Don't modify the source `leet-ssl-cert.yaml` in place — always write a timestamped sibling.
- Don't pick LE staging silently — only when the user asks.
