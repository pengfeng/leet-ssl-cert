# leet-ssl-cert

Automate TLS certificate lifecycle for domains that terminate SSL at a cloud load balancer:

**issue &rarr; store &rarr; upload &rarr; bind &rarr; renew**

Powered by ACME (Let's Encrypt) with DNS-01 challenges.

## Supported Providers

| Cloud | DNS | Deployers | Guide |
|---|---|---|---|
| Alibaba Cloud | Aliyun DNS | CLB, ALB | [Aliyun Guide](docs/aliyun.guide.md) |
| AWS | Route 53 | ACM, ELB/ALB | [AWS Guide](docs/aws.guide.md) |
| GCP | Cloud DNS | *(planned)* | [GCP Guide](docs/gcp.guide.md) |

## Requirements

- Python 3.11+
- DNS control for the target domain
- Cloud credentials for the selected provider

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate

# With a specific provider
pip install '.[aliyun]'    # Alibaba Cloud
pip install '.[aws]'       # AWS

# Or everything
pip install '.[all]'
```

## Quick Start

### 1. Set credentials

See the provider guide for your cloud: [Aliyun](docs/aliyun.guide.md) | [AWS](docs/aws.guide.md)

### 2. Create a config file

Generate one interactively:

```bash
leet-ssl-cert init
```

Or copy the example and edit it:

```bash
cp config/example.yaml ./leet-ssl-cert.yaml
```

### 3. Issue a certificate

```bash
leet-ssl-cert issue
```

### 4. Deploy to your load balancer

```bash
leet-ssl-cert deploy
```

### 5. Or run the full cycle at once

```bash
leet-ssl-cert run
```

### 6. Set up automatic renewal

```bash
leet-ssl-cert cron
```

## Commands

| Command | What it does |
|---|---|
| `init` | Generate a config file interactively |
| `issue` | Obtain or renew certificates via ACME |
| `deploy` | Upload certs and bind them to load balancers |
| `run` | `issue` + `deploy` in one step |
| `check` | Report local certificate status |
| `revoke` | Revoke a certificate through ACME |
| `cron` | Print a cron line for unattended renewal |

### Useful Flags

```bash
issue --dry-run          # Preview without changing state
issue --force            # Renew even if not expiring soon
issue --name my-site     # Target a single certificate
run --dry-run            # Check issuance path without deploying
deploy --name my-site    # Deploy only one certificate
init --skip-validation   # Skip provider credential checks
init --concise           # Short prompts without explanations
```

## Configuration

The CLI looks for config in this order:

1. `--config /path/to/config.yaml`
2. `./leet-ssl-cert.yaml` (current directory)
3. `~/.leet-ssl-cert/config.yaml`

Minimal example:

```yaml
account:
  email: admin@example.com

acme:
  directory_url: https://acme-v02.api.letsencrypt.org/directory

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

Environment variables in `${VAR_NAME}` form are resolved at load time. See [config/example.yaml](config/example.yaml) for a full example.

For provider-specific config fields (regions, listener IDs, load balancer IDs), see the provider guides:
- [Alibaba Cloud (Aliyun)](docs/aliyun.guide.md)
- [AWS](docs/aws.guide.md)
- [GCP](docs/gcp.guide.md) *(planned)*

## Local State

Files are stored under `~/.leet-ssl-cert/` by default:

```
~/.leet-ssl-cert/
  account.key
  certs/
    my-site/
      my-site.key
      my-site.pem
      my-site.meta.json
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'
pytest -q
```
