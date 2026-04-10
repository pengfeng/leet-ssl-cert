# leet-ssl-cert

`leet-ssl-cert` is a Python CLI for automating the certificate lifecycle for domains that terminate TLS at a cloud load balancer:

`issue cert -> store locally -> upload -> bind -> renew`

The current implementation covers the Phase 2 scope from the PRD:

- ACME DNS-01 issuance with Let's Encrypt-compatible servers
- Local certificate and metadata storage
- DNS providers for Alibaba Cloud DNS, Cloudflare, and AWS Route 53
- Deployers for Alibaba Cloud CLB, Alibaba Cloud ALB, AWS ACM, and AWS ELB/ALB listeners
- CLI commands for `init`, `issue`, `deploy`, `run`, `check`, `revoke`, and `cron`

## Support Matrix

| Area | Supported |
|---|---|
| DNS providers | `aliyun`, `cloudflare`, `aws` |
| Deployers | `aliyun_clb`, `aliyun_alb`, `aws_acm`, `aws_elb` |
| ACME challenge type | DNS-01 |
| ACME key type | RSA |

## Requirements

- Python `3.11+`
- Access to an ACME server such as Let's Encrypt
- DNS control for the target domain
- Cloud credentials for the selected provider

## Install

Install the base package:

```bash
pip install .
```

For Alibaba Cloud DNS + CLB support:

```bash
pip install '.[aliyun]'
```

For AWS support:

```bash
pip install '.[aws]'
```

For Cloudflare support:

```bash
pip install '.[cloudflare]'
```

For all optional integrations:

```bash
pip install '.[all]'
```

When running from a source checkout without installing the package, use:

```bash
PYTHONPATH=src python -m leet_ssl_cert --help
```

## Configuration

The CLI looks for config in this order:

1. `--config /path/to/config.yaml`
2. `./leet-ssl-cert.yaml`
3. `~/.leet-ssl-cert/config.yaml`

Example:

```yaml
account:
  email: admin@example.com

acme:
  directory_url: https://acme-v02.api.letsencrypt.org/directory
  key_size: 2048
  renewal_days: 30

storage:
  base_dir: ~/.leet-ssl-cert/certs

certificates:
  - name: my-site
    domains:
      - example.com
      - www.example.com
    dns_provider: aliyun
    deploy:
      - provider: aliyun_clb
        region: cn-hangzhou
        load_balancer_id: lb-xxxxxxxxxxxxx
        listener_port: 443

  - name: api-site
    domains:
      - api.example.com
    dns_provider: cloudflare
    deploy:
      - provider: aws_acm
        region: us-east-1

providers:
  aliyun:
    access_key_id: ${ALICLOUD_ACCESS_KEY_ID}
    access_key_secret: ${ALICLOUD_ACCESS_KEY_SECRET}
  cloudflare:
    api_token: ${CLOUDFLARE_API_TOKEN}
  aws: {}
```

Environment variables in `${VAR_NAME}` form are resolved at load time.
For AWS, leaving `providers.aws` empty uses the standard boto3 credential chain.

You can start from [`config/example.yaml`](config/example.yaml).

Provider notes:

- `aliyun`: expects `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`
- `cloudflare`: expects `CLOUDFLARE_API_TOKEN`
- `aws`: can use the normal boto3 credential chain, including env vars, `~/.aws/credentials`, profiles, or IAM role credentials

Deployer notes:

- `aliyun_clb`: requires `region`, `load_balancer_id`, and `listener_port`
- `aliyun_alb`: requires `region` and `listener_id`
- `aws_acm`: requires `region`
- `aws_elb`: requires `region` and either `listener_arn` for ELBv2/ALB or `load_balancer_name` for Classic ELB

## Quick Start

Set credentials:

```bash
export ALICLOUD_ACCESS_KEY_ID=your-access-key-id
export ALICLOUD_ACCESS_KEY_SECRET=your-access-key-secret
```

Create a config file:

```bash
cp config/example.yaml ./leet-ssl-cert.yaml
```

Or generate one interactively:

```bash
PYTHONPATH=src python -m leet_ssl_cert init --skip-validation
```

If you want a shorter setup flow without the plain-English explanations:

```bash
PYTHONPATH=src python -m leet_ssl_cert init --concise --skip-validation
```

Generate and validate provider credentials in one step:

```bash
PYTHONPATH=src python -m leet_ssl_cert init \
  --email admin@example.com \
  --name my-site \
  --domains example.com,www.example.com \
  --dns-provider cloudflare \
  --deployer aws_acm \
  --region us-east-1
```

During interactive setup:

- the tool asks for the DNS provider and deployment provider first when validation is enabled
- required environment variables are checked before the rest of the setup questions so you do not waste time filling in fields only to fail later
- the prompts explain each item in plain English by default
- `--concise` suppresses those extra explanations
- region prompts show a few common regions first and allow a custom region code if yours is not listed
- prompt answers are saved in `.leet/.init-inputs.json` so the next `init` run can prefill them
- validation now checks required environment variables before making provider API calls and prints the current values it found

Check the planned state:

```bash
PYTHONPATH=src python -m leet_ssl_cert check
```

Issue or renew certificates:

```bash
PYTHONPATH=src python -m leet_ssl_cert issue
```

Deploy existing local certificates:

```bash
PYTHONPATH=src python -m leet_ssl_cert deploy
```

Run the full cycle:

```bash
PYTHONPATH=src python -m leet_ssl_cert run
```

Generate a cron entry:

```bash
PYTHONPATH=src python -m leet_ssl_cert cron
```

Revoke a local certificate via ACME:

```bash
PYTHONPATH=src python -m leet_ssl_cert revoke --name my-site
```

## Commands

```bash
python -m leet_ssl_cert issue [--name NAME] [--force] [--dry-run]
python -m leet_ssl_cert deploy [--name NAME]
python -m leet_ssl_cert run [--name NAME] [--force] [--dry-run]
python -m leet_ssl_cert check [--name NAME]
python -m leet_ssl_cert revoke --name NAME
python -m leet_ssl_cert init [--output FILE] [--skip-validation]
python -m leet_ssl_cert cron [--schedule "0 2 * * *"]
```

Command behavior:

- `issue`: obtains or renews certificates and stores them locally
- `deploy`: uploads local certs and binds them to configured targets
- `run`: executes `issue` then `deploy`
- `check`: reports whether local certs exist and whether they are due for renewal
- `revoke`: revokes a locally stored certificate through the configured ACME account
- `init`: generates a config file and can validate cloud credentials before writing it
- `cron`: prints the cron line for unattended renewal

Useful options:

- `issue --dry-run`: shows which certificates would be issued or renewed without changing state
- `issue --force`: renews even if the current local certificate is not close to expiry
- `run --dry-run`: checks the issuance path without deploying
- `deploy --name NAME`: deploys only one logical certificate
- `check --name NAME`: limits the report to one certificate
- `init --force`: overwrites an existing config file
- `init --skip-validation`: writes config without testing provider credentials
- `init --concise`: keeps interactive prompts short and skips the extra explanations

## Local State

By default, files are stored under `~/.leet-ssl-cert/`:

```text
~/.leet-ssl-cert/
  account.key
  certs/
    my-site/
      my-site.key
      my-site.pem
      my-site.meta.json
```

`account.key` and private keys are written with restrictive file permissions.

`*.meta.json` stores certificate dates and deploy metadata so `check` can report current local status.

## Environment Checks

When a command uses environment-backed configuration, the tool now performs a preflight check before continuing.

It prints:

- the environment variables used by the current operation
- a plain-English definition for each variable
- the value currently detected for each variable

If a required variable is missing, the command exits early with a clear error after printing the full checklist.

## Development

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
./.venv/bin/pip install click pyyaml cryptography pytest acme josepy dnspython
```

Run tests:

```bash
./.venv/bin/python -m pytest -q
```

Show CLI help from source:

```bash
PYTHONPATH=src ./.venv/bin/python -m leet_ssl_cert --help
```

## Current Scope

The README reflects the implemented CLI, not the full future PRD surface.

Implemented:

- `init`
- `issue`
- `deploy`
- `run`
- `check`
- `revoke`
- `cron`
- `aliyun` DNS provider
- `cloudflare` DNS provider
- `aws` Route 53 DNS provider
- `aliyun_clb` deployer
- `aliyun_alb` deployer
- `aws_acm` deployer
- `aws_elb` deployer

Not implemented yet:

- automatic cron installation
- additional providers beyond the Phase 2 scope
- notification/webhook integrations
- Docker packaging / sidecar workflow
