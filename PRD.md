# PRD: leet-ssl-cert

**Automated SSL Certificate Provisioning & Cloud Deployment**

## Problem

Managing free SSL certificates (Let's Encrypt) for domains behind cloud load balancers (Alibaba Cloud CLB, AWS ELB, etc.) is painful:

1. You must manually run an ACME client to obtain the cert
2. DNS-01 challenges require calling cloud DNS APIs to create TXT records
3. The resulting PEM files must be manually uploaded to the cloud provider's certificate store
4. The certificate must be bound to the correct HTTPS listener
5. Every 90 days, you repeat all of the above

**acmebot** (the reference project) solves certificate issuance well but delegates cloud deployment to shell hooks, requires nsupdate for DNS, and carries significant complexity (HPKP, DANE/TLSA, CT logs, OCSP stapling, master/follower mode) that is unnecessary for the cloud load balancer use case.

## Goal

A focused Python CLI tool that **fully automates** the cycle:

```
obtain cert (Let's Encrypt) --> upload cert --> bind to cloud resource --> auto-renew
```

with **native cloud SDK integrations** (not shell hooks) for both DNS challenges and certificate deployment.

## Non-Goals

- Replacing a general-purpose ACME client (Certbot, acmebot)
- Managing certificates for local web servers (nginx, Apache)
- HPKP, DANE/TLSA, CT log submission, OCSP stapling
- Master/follower or multi-server coordination
- HTTP-01 challenge support (DNS-01 only; the target use case is load balancers where HTTP challenges are awkward)

---

## Architecture

```
leet-ssl-cert/
  src/
    leet_ssl_cert/
      __init__.py
      cli.py                  # CLI entry point (click)
      config.py               # Config loading & validation
      acme_client.py          # ACME protocol interactions (issue, renew)
      dns/                    # DNS challenge providers (plugin system)
        __init__.py
        base.py               # Abstract DNS provider interface
        aliyun.py             # Alibaba Cloud DNS (alidns)
        aws.py                # AWS Route 53
        cloudflare.py         # Cloudflare DNS
      deployer/               # Certificate deployers (plugin system)
        __init__.py
        base.py               # Abstract deployer interface
        aliyun_clb.py         # Alibaba Cloud CLB (Classic Load Balancer)
        aliyun_alb.py         # Alibaba Cloud ALB (Application Load Balancer)
        aws_elb.py            # AWS ELB / ALB
        aws_acm.py            # AWS ACM (Certificate Manager)
      storage.py              # Local cert/key file management
      scheduler.py            # Renewal scheduling (cron generation)
  config/
    example.yaml              # Example configuration
  tests/
  pyproject.toml
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| DNS-01 only | Target is cloud LBs where the domain already points at the LB; HTTP-01 would require routing the challenge through the LB. DNS-01 is universally applicable. |
| Native cloud SDKs, not shell hooks | Hooks are fragile, hard to test, and push integration complexity onto the user. Native SDK calls give structured errors, retries, and type safety. |
| Plugin-based providers | Adding a new cloud is one file implementing an interface. No changes to core logic. Mirrors how acmebot isolates concerns, but with Python ABCs instead of hook strings. |
| Single YAML config | acmebot's config is powerful but complex (400+ line examples). We flatten to one file with clear sections. |
| RSA-only by default | Simplicity. ECDSA can be added later; RSA is universally supported by all cloud LBs today. |

---

## Configuration

```yaml
# ~/.leet-ssl-cert/config.yaml  or  ./leet-ssl-cert.yaml

account:
  email: admin@example.com

acme:
  directory_url: https://acme-v02.api.letsencrypt.org/directory  # default
  # directory_url: https://acme-staging-v02.api.letsencrypt.org/directory  # for testing
  key_size: 2048            # RSA key size for certificates
  renewal_days: 30          # renew when fewer than N days remain

storage:
  base_dir: ~/.leet-ssl-cert/certs   # where certs/keys are stored locally

certificates:
  - name: my-site                     # logical name, used for file naming & logging
    domains:
      - example.com
      - www.example.com
    dns_provider: aliyun              # which DNS plugin to use for challenges
    deploy:
      - provider: aliyun_clb          # which deployer plugin to use
        listener_port: 443            # HTTPS listener port to bind
        # provider-specific fields:
        region: cn-hangzhou
        load_balancer_id: lb-xxxxxxxxxxxxx

  - name: api-site
    domains:
      - api.example.com
    dns_provider: cloudflare
    deploy:
      - provider: aws_acm
        region: us-east-1

# Provider credentials (can also come from env vars or cloud credential files)
providers:
  aliyun:
    access_key_id: ${ALIBABA_CLOUD_ACCESS_KEY_ID}
    access_key_secret: ${ALIBABA_CLOUD_ACCESS_KEY_SECRET}
  cloudflare:
    api_token: ${CLOUDFLARE_API_TOKEN}
  aws:
    # Uses default boto3 credential chain (env, ~/.aws/credentials, IAM role)
```

### Environment Variable Interpolation

Config values like `${VAR_NAME}` are resolved from environment variables at load time, so secrets never need to be in the config file.

---

## Core Workflow

### 1. Issue / Renew Certificate (`leet-ssl-cert issue`)

Modeled after acmebot's `process_authorizations()` + `process_certificates()` flow, but streamlined:

```
For each certificate in config:
  1. Check if local cert exists and is not due for renewal
     - If valid and not expiring soon: skip (unless --force)
  2. Generate RSA private key (or reuse existing)
  3. Create ACME order for all domains in the certificate
  4. For each domain authorization:
     a. Extract dns-01 challenge token + response
     b. Call dns_provider.create_txt_record(
            zone, "_acme-challenge.{domain}", response)
     c. Poll DNS until TXT record is visible (like acmebot's
        _lookup_dns_challenge: max 60 attempts, 10s delay)
  5. Answer all challenges with ACME server
  6. Poll order until status is VALID (like acmebot's _poll_order)
  7. Download certificate chain
  8. Save locally:
     - {name}.key       (private key, PEM)
     - {name}.pem       (full chain certificate, PEM)
  9. Clean up DNS TXT records:
     dns_provider.delete_txt_record(zone, "_acme-challenge.{domain}")
```

**Key reference from acmebot:**
- Account key management: `connect_client()` (line ~2061) -- register/load ACME account key
- CSR generation: `generate_csr()` (line ~1845) -- build CSR with SANs
- Challenge flow: `_handle_authorizations()` (line ~2241) -- extract challenge, set DNS, answer
- DNS verification: `_lookup_dns_challenge()` (line ~1170) -- poll nameservers
- Order polling: `_poll_order()` (line ~2509) -- wait for cert

### 2. Deploy Certificate (`leet-ssl-cert deploy`)

After issuance (or independently for already-issued certs):

```
For each certificate in config:
  For each deploy target:
    1. Read local cert + key PEM files
    2. Call deployer.upload_certificate(name, cert_pem, key_pem)
       - Returns a certificate_id from the cloud provider
    3. Call deployer.bind_certificate(certificate_id, listener_config)
    4. Optionally: deployer.cleanup_old_certificates(name)
       - Remove previously uploaded certs for this name
         (keep current + one previous for rollback)
```

**Example: Alibaba Cloud CLB deployer flow:**

```python
# 1. Upload cert to SLB certificate store
slb_client.upload_server_certificate(
    server_certificate_name=f"leet-{name}-{timestamp}",
    server_certificate=cert_pem,      # fullchain.pem content
    private_key=key_pem,              # privkey.pem content
    region_id=region,
)

# 2. Set the certificate on the HTTPS listener
slb_client.set_listener_attribute(
    load_balancer_id=lb_id,
    listener_port=443,
    server_certificate_id=new_cert_id,
)

# 3. Delete old certificate (optional)
slb_client.delete_server_certificate(
    server_certificate_id=old_cert_id,
)
```

### 3. Full Cycle (`leet-ssl-cert run`)

Combines issue + deploy in one command. This is the command you put in cron.

### 4. Renew Check (`leet-ssl-cert check`)

Dry-run: reports which certs are expiring and what would happen. No mutations.

---

## Plugin Interfaces

### DNS Provider

```python
from abc import ABC, abstractmethod

class DNSProvider(ABC):
    """Interface for DNS challenge providers."""

    @abstractmethod
    def create_txt_record(self, zone: str, record_name: str, value: str) -> None:
        """Create a TXT record for ACME dns-01 challenge."""
        ...

    @abstractmethod
    def delete_txt_record(self, zone: str, record_name: str, value: str) -> None:
        """Delete the TXT record after challenge is complete."""
        ...

    @abstractmethod
    def find_zone_for_domain(self, domain: str) -> str:
        """Given a domain (e.g. www.example.com), return the zone (e.g. example.com).
        May query the provider's zone list to determine this."""
        ...
```

### Certificate Deployer

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class DeployResult:
    certificate_id: str          # Cloud provider's cert ID
    provider: str                # e.g. "aliyun_clb"
    bound_to: str                # e.g. "lb-xxx:443"
    old_certificate_id: str | None  # Previous cert that was replaced

class CertificateDeployer(ABC):
    """Interface for certificate deployment targets."""

    @abstractmethod
    def upload_certificate(self, name: str, cert_pem: str, key_pem: str) -> str:
        """Upload cert+key to cloud provider. Returns certificate_id."""
        ...

    @abstractmethod
    def bind_certificate(self, certificate_id: str) -> DeployResult:
        """Bind the certificate to the target resource (listener, distribution, etc.)."""
        ...

    @abstractmethod
    def cleanup_old_certificates(self, name: str, keep: int = 1) -> list[str]:
        """Remove old certificates for this logical name, keeping N most recent.
        Returns list of deleted certificate IDs."""
        ...
```

---

## CLI Commands

```
leet-ssl-cert issue [--name NAME] [--force] [--dry-run]
    Issue or renew certificates. If --name given, only process that cert.

leet-ssl-cert deploy [--name NAME]
    Deploy locally-stored certificates to cloud providers.

leet-ssl-cert run [--name NAME] [--force]
    Full cycle: issue + deploy. Intended for cron.

leet-ssl-cert check
    Report certificate status (local + cloud). No mutations.

leet-ssl-cert revoke --name NAME
    Revoke a certificate via ACME.

leet-ssl-cert init
    Interactive setup: create config file, test provider credentials.

leet-ssl-cert cron [--install] [--schedule "0 2 * * *"]
    Generate or install a cron entry for automatic renewal.
```

---

## State & Storage

```
~/.leet-ssl-cert/
  config.yaml                 # main config
  account.key                 # ACME account private key (auto-generated)
  certs/
    my-site/
      my-site.key             # private key (PEM)
      my-site.pem             # fullchain certificate (PEM)
      my-site.meta.json       # metadata: expiry, domains, last deploy info
    api-site/
      api-site.key
      api-site.pem
      api-site.meta.json
```

`meta.json` example:
```json
{
  "domains": ["example.com", "www.example.com"],
  "not_before": "2026-04-08T00:00:00Z",
  "not_after": "2026-07-07T00:00:00Z",
  "serial": "03:ab:cd:...",
  "last_deploy": {
    "aliyun_clb": {
      "certificate_id": "cert-xxxxx",
      "deployed_at": "2026-04-08T12:00:00Z",
      "load_balancer_id": "lb-xxxxx",
      "listener_port": 443
    }
  }
}
```

---

## Error Handling

Following the project's global convention: exceptions propagate with full stack traces. No swallowing errors with bare `print()`.

Specific error categories (inspired by acmebot's `ErrorCode` enum):
- **ConfigError** -- invalid config, missing credentials
- **ACMEError** -- ACME protocol failures (rate limit, authorization denied)
- **DNSError** -- DNS record creation/propagation failures
- **DeployError** -- cloud API failures during upload/bind

All operations that mutate state (DNS records, cloud certs) have corresponding **cleanup/rollback** on failure:
- If DNS TXT creation succeeds but ACME challenge fails: delete the TXT record
- If cert upload succeeds but bind fails: log the orphaned cert ID for manual cleanup

---

## Dependencies

```toml
[project]
dependencies = [
    "acme >= 2.0.0",         # ACME protocol client (same as acmebot)
    "cryptography >= 42.0",   # Key generation, CSR, cert parsing
    "josepy >= 1.0.0",        # ACME JSON serialization (same as acmebot)
    "click >= 8.0",           # CLI framework
    "pyyaml >= 6.0",          # Config parsing
    "dnspython >= 2.4",       # DNS lookups for challenge verification
]

[project.optional-dependencies]
aliyun = [
    "alibabacloud-slb20140515",       # Alibaba Cloud SLB (CLB) SDK
    "alibabacloud-alb20200616",       # Alibaba Cloud ALB SDK
    "alibabacloud-alidns20150109",    # Alibaba Cloud DNS SDK
    "alibabacloud-cas20200407",       # Alibaba Cloud Certificate Service SDK
    "alibabacloud-tea-openapi",       # Alibaba Cloud OpenAPI core
]
aws = [
    "boto3 >= 1.26",                  # AWS SDK
]
cloudflare = [
    "cloudflare >= 3.0",              # Cloudflare SDK
]
all = ["leet-ssl-cert[aliyun,aws,cloudflare]"]
```

---

## Initial Provider Support (MVP)

### Phase 1 -- MVP
- **DNS providers:** Alibaba Cloud DNS (alidns)
- **Deployers:** Alibaba Cloud CLB
- **CLI:** `issue`, `deploy`, `run`, `check`

### Phase 2
- **DNS providers:** Cloudflare, AWS Route 53
- **Deployers:** Alibaba Cloud ALB, AWS ACM, AWS ELB
- **CLI:** `init`, `cron`, `revoke`

### Phase 3
- **Deployers:** Tencent Cloud CLB, CDN providers (Alibaba Cloud CDN, CloudFront)
- Webhook/notification on renewal (email, Slack, DingTalk)
- Docker image for running as a sidecar or cron container

---

## Key Lessons from acmebot

| What to keep | What to simplify |
|---|---|
| ACME v2 protocol via `acme` library (proven, battle-tested) | Drop the 3600-line monolith; modular package instead |
| DNS challenge verification polling (max attempts + delay) | Replace nsupdate with native cloud DNS SDK calls |
| Atomic file writes (`FileTransaction` pattern) | Drop HPKP, DANE/TLSA, CT logs, OCSP (not needed for cloud LBs) |
| Account key persistence & registration flow | Drop master/follower mode |
| Full certificate chain handling (not just leaf) | Drop dual RSA+ECDSA (RSA default, ECDSA optional later) |
| Configurable ACME directory URL (staging vs production) | Drop shell hooks; native SDK integrations instead |
| Structured error codes for different failure modes | Simpler flat YAML config instead of deeply nested JSON |

---

## Security Considerations

1. **Private keys** are written with 0600 permissions and never logged
2. **Cloud credentials** come from env vars or cloud credential files, not the config file directly (the `${VAR}` syntax is resolved at runtime)
3. **ACME account key** is stored locally with 0600 permissions
4. **No secrets in meta.json** -- only IDs and timestamps
5. The tool never sends private keys anywhere except to the cloud provider's certificate upload API over HTTPS

---

## Example End-to-End Usage

```bash
# 1. Install
pip install leet-ssl-cert[aliyun]

# 2. Set credentials
export ALIBABA_CLOUD_ACCESS_KEY_ID=xxx
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=xxx

# 3. Create config
cat > leet-ssl-cert.yaml << 'EOF'
account:
  email: admin@example.com

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
    access_key_id: ${ALIBABA_CLOUD_ACCESS_KEY_ID}
    access_key_secret: ${ALIBABA_CLOUD_ACCESS_KEY_SECRET}
EOF

# 4. Test with staging first
leet-ssl-cert run --dry-run

# 5. Issue + deploy
leet-ssl-cert run

# 6. Set up auto-renewal
leet-ssl-cert cron --install
# Installs: 0 2 * * * leet-ssl-cert run --config ~/.leet-ssl-cert/config.yaml
```

---

## Success Metrics

- A user with an Alibaba Cloud CLB and a domain can go from zero to a working HTTPS listener in **under 5 minutes** (excluding DNS propagation)
- Renewal runs unattended with zero manual intervention
- Adding a new cloud provider requires implementing **2 files** (DNS provider + deployer), no core changes
