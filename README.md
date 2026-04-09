# leet-ssl-cert

`leet-ssl-cert` is a Python CLI for automating the certificate lifecycle for domains that terminate TLS at a cloud load balancer:

`issue cert -> store locally -> upload -> bind -> renew`

The current MVP focuses on:

- ACME DNS-01 issuance with Let's Encrypt-compatible servers
- Local certificate and metadata storage
- Alibaba Cloud DNS for challenge records
- Alibaba Cloud CLB for certificate deployment
- CLI commands for `issue`, `deploy`, `run`, `check`, and `cron`

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

providers:
  aliyun:
    access_key_id: ${ALICLOUD_ACCESS_KEY_ID}
    access_key_secret: ${ALICLOUD_ACCESS_KEY_SECRET}
```

Environment variables in `${VAR_NAME}` form are resolved at load time.

You can start from [`config/example.yaml`](config/example.yaml).

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

## Commands

```bash
python -m leet_ssl_cert issue [--name NAME] [--force] [--dry-run]
python -m leet_ssl_cert deploy [--name NAME]
python -m leet_ssl_cert run [--name NAME] [--force] [--dry-run]
python -m leet_ssl_cert check [--name NAME]
python -m leet_ssl_cert cron [--schedule "0 2 * * *"]
```

Command behavior:

- `issue`: obtains or renews certificates and stores them locally
- `deploy`: uploads local certs and binds them to configured targets
- `run`: executes `issue` then `deploy`
- `check`: reports whether local certs exist and whether they are due for renewal
- `cron`: prints the cron line for unattended renewal

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

- `issue`
- `deploy`
- `run`
- `check`
- `cron`
- `aliyun` DNS provider
- `aliyun_clb` deployer

Not implemented yet:

- `init`
- `revoke`
- Cloudflare and AWS providers
- Additional deployers such as ALB and ACM
