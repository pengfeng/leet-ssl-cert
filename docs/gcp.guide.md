# Google Cloud (GCP) Provider Guide

> **Status**: GCP support is not yet implemented in `leet-ssl-cert`. This guide describes the planned scope and the GCP SDKs / credentials that will be used.

## Planned Support

| Feature | GCP SDK | Status |
|---|---|---|
| Cloud DNS (DNS-01 challenges) | `google-cloud-dns` | Planned |
| Certificate Manager deployment | `google-cloud-certificate-manager` | Planned |
| Cloud Load Balancing binding | `google-cloud-compute` | Planned |

## Install (Preview)

Once implemented, GCP support will be installed via:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install '.[gcp]'
```

This will pull in the Google Cloud Python SDKs listed above.

## Credentials

All Google Cloud Python SDKs authenticate via [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials). You can provide credentials in several ways:

### Option 1 -- Service Account Key (recommended for servers)

1. Go to [GCP Console > IAM > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Select or create a service account
3. Go to **Keys** > **Add Key** > **Create new key** > **JSON**
4. Save the downloaded JSON file and set the environment variable:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GCP_PROJECT=your-project-id
```

### Option 2 -- gcloud CLI (for local development)

```bash
gcloud auth application-default login
gcloud config set project your-project-id
```

### Option 3 -- Workload Identity (on GCP compute)

No configuration needed. The SDK automatically picks up credentials on GKE, Cloud Run, Compute Engine, and Cloud Functions.

### Required IAM Roles

| Feature | IAM Role |
|---|---|
| Cloud DNS | `roles/dns.admin` |
| Certificate Manager | `roles/certificatemanager.editor` |
| Load Balancing | `roles/compute.loadBalancerAdmin` |

## GCP Load Balancer Products

For reference, these are the GCP load balancer types where TLS termination applies:

### External Application Load Balancer (HTTP/S)

- The most common choice for HTTPS workloads
- TLS certificates are managed through **Certificate Manager** or the older **SSL Certificates** resource
- Supports both Google-managed and self-managed certificates
- Console: [Load Balancing](https://console.cloud.google.com/net-services/loadbalancing)

### Regional External Application Load Balancer

- Same as above but scoped to a single region
- Uses the same certificate management approach

### External Proxy Network Load Balancer (SSL Proxy)

- Layer 4 TLS termination
- Uses the same SSL certificate resources

### Key Concepts

- **Target HTTPS Proxy**: the resource that holds the SSL certificate reference for HTTP/S load balancers
- **Certificate Manager Certificate Map**: the newer way to map certificates to load balancers
- **SSL Certificate resource**: the legacy way to attach certificates (still widely used)

## Config (Preview)

The config format will follow the same pattern as other providers:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
    dns_provider: gcp
    deploy:
      - provider: gcp_lb
        project: my-gcp-project
        target_https_proxy: my-proxy

providers:
  gcp:
    project: ${GCP_PROJECT}
```

## Contributing

If you would like to contribute GCP support, create a new provider plugin at `src/leet_ssl_cert/providers/gcp/`:

- `dns.py`: subclass `DNSProvider` from `leet_ssl_cert.providers.base`
- `lb.py`: subclass `CertificateDeployer` from `leet_ssl_cert.providers.base`
- `__init__.py`: register implementations with `register_dns_provider` and `register_deployer`

See the existing `providers/aws/` and `providers/aliyun/` packages for reference.
