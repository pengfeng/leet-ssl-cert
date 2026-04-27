---
name: leet-ssl-cert-deploy
description: Upload and bind an already-issued certificate to a cloud load balancer using leet-ssl-cert. Use when the user asks to deploy, attach, bind, or upload a cert to Aliyun (CLB/ALB), AWS (ACM/ELB), or a GCP load balancer. The only required input is the load balancer target identifier; everything else comes from .env defaults or sensible presets.
---

# leet-ssl-cert: deploy a certificate

Push an issued cert to a cloud load balancer via `leet-ssl-cert deploy`. Run the `leet-ssl-cert-create` skill first if no cert exists yet.

## When to use

The user says things like "deploy the cert to my load balancer", "attach my cert to lb-bp1abc...", "bind the cert on edge-proxy", "upload the cert to ACM", "set the cert on listener arn:...".

## Required input (exactly one of these)

The required field also picks the cloud and deployer:

| Field user provided | Cloud | Deployer | Notes |
|---|---|---|---|
| `load_balancer_id` (e.g., `lb-bp1...`) | Aliyun | `aliyun_clb` | |
| `listener_id` (e.g., `lsn-bp1...`) | Aliyun | `aliyun_alb` | |
| `target_https_proxy` (a name) | GCP | `gcp_lb` | |
| `target_ssl_proxy` (a name) | GCP | `gcp_lb` | Implies `scope=global` (regional only supports `target_https_proxy`). |
| `listener_arn` (an ELBv2 ARN) | AWS | `aws_elb` | Modern ALB/NLB. Region parsed from the ARN. |
| `load_balancer_name` (a Classic ELB name) | AWS | `aws_elb` | Classic ELB. Needs `region`. |
| `acm_region` (an AWS region, ACM-only) | AWS | `aws_acm` | Use when the user wants the cert imported to ACM with no LB binding (e.g., for CloudFront). |

If two of these are given, ask the user which one to deploy to. If none is given, ask once. If the user says "deploy to AWS ACM in us-east-1" without specifying a listener, treat it as `acm_region=us-east-1`.

## Optional inputs

Resolve from defaults; ask only if missing after all sources are checked.

| Field | When | Default |
|---|---|---|
| `name` | Always | If the source config has exactly one cert, use it. Otherwise list and ask. |
| `region` | Aliyun | `LEET_SSL_CERT_REGION` → `ALIBABA_CLOUD_REGION_ID` → cache `region` → `cn-hangzhou`. |
| `listener_port` | Aliyun CLB | `LEET_SSL_CERT_LISTENER_PORT` → 443. |
| `region` | AWS | Parsed from `listener_arn` if present, else `LEET_SSL_CERT_REGION` → `AWS_REGION` → `AWS_DEFAULT_REGION` → `us-east-1`. |
| `project` | GCP | `LEET_SSL_CERT_GCP_PROJECT` → `GOOGLE_CLOUD_PROJECT` → existing config's `providers.gcp.project` → cache. |
| `scope` | GCP | `LEET_SSL_CERT_GCP_SCOPE` → `global`. (Regional only allowed for `target_https_proxy`.) |

## Defaults resolution order

The CLI auto-loads `./.env` and `~/.leet-ssl-cert/.env` at startup (existing process env vars always win). For each unspecified field, walk in order:

1. Skill argument.
2. Process env / `.env` keys (table below).
3. Existing source `leet-ssl-cert.yaml` (cwd, then `~/.leet-ssl-cert/config.yaml`). Reuse `providers.<cloud>` and any existing `deploy:` entry of the same kind on the same cert (so re-deploys carry forward `region`, `scope`, etc.).
4. `.leet/.init-inputs.json` cache.
5. Hardcoded fallbacks above.

### `.env` keys read by this skill

| Key | Meaning |
|---|---|
| `LEET_SSL_CERT_NAME` | Default cert name when ambiguous. |
| `LEET_SSL_CERT_REGION` | Default cloud region (Aliyun and AWS). |
| `LEET_SSL_CERT_LISTENER_PORT` | Default Aliyun CLB listener port. |
| `LEET_SSL_CERT_GCP_PROJECT` | Default GCP project. |
| `LEET_SSL_CERT_GCP_SCOPE` | Default GCP LB scope (`global` or a region). |

Provider creds are kept under their conventional names below.

## Credential check

After the cloud is known, verify env vars (the CLI's `.env` autoloader has already run). Do **not** call `gcloud`, `aws`, or `aliyun`.

| Cloud | Required env vars |
|---|---|
| Aliyun (CLB or ALB) | `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_ACCESS_KEY_SECRET` |
| AWS (ACM or ELB) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (or `AWS_DEFAULT_REGION`); `AWS_PROFILE` is also acceptable. |
| GCP | `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT` |

If any are missing, stop and print the `export …` lines plus a pointer to the matching guide in [docs/](../../docs/).

## Steps

1. **Locate the source config**: `./leet-ssl-cert.yaml`, fall back to `~/.leet-ssl-cert/config.yaml`. If neither exists, tell the user to run the create skill first and stop.
2. **Verify the CLI**: `leet-ssl-cert --help`. If missing, tell the user to `pip install -e '.[<cloud>]'` and stop.
3. **Determine cloud + deployer** from the required input.
4. **Resolve `name`.** If exactly one cert exists, use it. If multiple, list them and ask.
5. **Confirm the cert was issued.** Check `~/.leet-ssl-cert/certs/<name>/<name>.pem` exists. If not, stop and suggest running the create skill.
6. **Resolve all remaining fields** via the defaults order above.
7. **Verify creds** per the table.
8. **Build the deploy entry** in memory:

   Aliyun CLB:
   ```yaml
   - provider: aliyun_clb
     region: <region>
     load_balancer_id: <load_balancer_id>
     listener_port: <listener_port>
   ```
   Aliyun ALB:
   ```yaml
   - provider: aliyun_alb
     region: <region>
     listener_id: <listener_id>
   ```
   AWS ACM:
   ```yaml
   - provider: aws_acm
     region: <acm_region>
   ```
   AWS ELB (modern ALB/NLB):
   ```yaml
   - provider: aws_elb
     region: <region>
     listener_arn: <listener_arn>
   ```
   AWS ELB (Classic):
   ```yaml
   - provider: aws_elb
     region: <region>
     load_balancer_name: <load_balancer_name>
     listener_port: <listener_port|443>
   ```
   GCP:
   ```yaml
   - provider: gcp_lb
     project: <project>
     scope: <scope>
     target_https_proxy: <target_https_proxy>   # or target_ssl_proxy: <name>
   ```
9. **Compose the new config.** Start from the source, then:
   - Merge the deploy entry into the cert's `deploy:` list. If an entry with the same `provider` already exists on that cert, replace it. Otherwise append. Don't touch deploy entries for other providers.
   - Make sure `providers.<cloud>` exists (env-var references — see [config/example.yaml](../../config/example.yaml)).
10. **Write to a NEW timestamped sibling file** — never modify the source in place. Filename: `leet-ssl-cert.<YYYYMMDD-HHMMSS>.yaml` next to the source (or in cwd). Use `date +%Y%m%d-%H%M%S` for the timestamp.
11. **Preview.** Show:
    - Compact summary (name, cloud, deployer, target id, region/project, scope/port).
    - The path to the new config file.
    - The diff vs. the source config (`diff -u`).
    - Single `AskUserQuestion` with options "Proceed" / "Cancel".
12. **Run** against the new file:
    ```bash
    leet-ssl-cert --config <new-file> deploy --name <name>
    ```
13. **Report** the certificate id and what it was bound to from the CLI output, plus the path of the timestamped config used. Mention the user can promote it with `mv leet-ssl-cert.<ts>.yaml leet-ssl-cert.yaml`. If renewal isn't set up, mention `leet-ssl-cert cron`.
14. **Persist defaults to `./.env`.** For values like `LEET_SSL_CERT_REGION`, `LEET_SSL_CERT_GCP_PROJECT`, `LEET_SSL_CERT_GCP_SCOPE`, `LEET_SSL_CERT_LISTENER_PORT`, append/update `./.env` so future runs reuse them. Do not write secrets unless the user explicitly asked.

## Don'ts

- Don't run any cloud-vendor CLI. Only `leet-ssl-cert`.
- Don't collect secrets via prompts.
- Don't issue a new cert here — that's the create skill.
- Don't modify the source `leet-ssl-cert.yaml` in place — always a timestamped sibling.
- Don't replace deploy entries for *other* providers on the same cert; only the matching one.
