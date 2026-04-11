# Google Cloud (GCP) Provider Guide

This guide covers how to set up Google Cloud credentials and configure `leet-ssl-cert` for Cloud DNS validation and Google Cloud load balancer certificate deployment.

If your DNS is hosted outside Google Cloud, you can still use `gcp_lb` as the deployer. For GoDaddy specifically, see [GCP Load Balancer + GoDaddy DNS Guide](gcp-godaddy.guide.md).

## Supported Features

| Feature | GCP SDK | Status |
|---|---|---|
| Cloud DNS (DNS-01 challenges) | `google-cloud-dns` | Implemented |
| Self-managed SSL certificate upload | `google-cloud-compute` | Implemented |
| Target HTTPS Proxy binding | `google-cloud-compute` | Implemented |
| Target SSL Proxy binding | `google-cloud-compute` | Implemented |
| Certificate Manager / certificate maps | `google-cloud-certificate-manager` | Not yet implemented |

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install '.[gcp]'
```

## Credentials

The Google Cloud SDKs used by `leet-ssl-cert` authenticate through [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials).

### Option 1 -- Service Account Key

1. Go to [GCP Console > IAM > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Select or create a service account
3. Go to **Keys** > **Add Key** > **Create new key** > **JSON**
4. Save the downloaded JSON file and set:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GCP_PROJECT=your-project-id
```

### Option 2 -- gcloud CLI

```bash
gcloud auth application-default login
gcloud config set project your-project-id
```

### Option 3 -- Workload Identity

No additional configuration is needed on GKE, Cloud Run, Compute Engine, and other GCP runtimes that already expose ADC.

## Required IAM Roles

| Feature | IAM Role |
|---|---|
| Cloud DNS | `roles/dns.admin` |
| SSL certificate upload / HTTPS proxy binding | `roles/compute.loadBalancerAdmin` |

If you use GoDaddy DNS instead of Cloud DNS, you do not need the Cloud DNS role for this tool.

## Deployer Scope

The current GCP deployer is `gcp_lb`. It uses Compute Engine SSL certificate resources and can bind them to:

- Global `target_https_proxy`
- Regional `target_https_proxy`
- Global `target_ssl_proxy`

Certificate Manager certificate maps are not wired into this deployer yet.

## Config

### Global HTTPS proxy

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
      - www.example.com
    dns_provider: gcp
    deploy:
      - provider: gcp_lb
        project: my-gcp-project
        scope: global
        target_https_proxy: edge-proxy

providers:
  gcp:
    project: ${GCP_PROJECT}
```

### Regional HTTPS proxy

```yaml
certificates:
  - name: regional-site
    domains:
      - regional.example.com
    dns_provider: gcp
    deploy:
      - provider: gcp_lb
        project: my-gcp-project
        scope: regional
        region: us-central1
        target_https_proxy: regional-edge-proxy
```

### Global SSL proxy

```yaml
certificates:
  - name: tcp-site
    domains:
      - tcp.example.com
    dns_provider: gcp
    deploy:
      - provider: gcp_lb
        project: my-gcp-project
        scope: global
        target_ssl_proxy: ssl-proxy
```

## Init Examples

```bash
leet-ssl-cert init gcp

# Or pass the deployment target directly
leet-ssl-cert init gcp \
  --dns-provider gcp \
  --deployer gcp_lb \
  --project my-gcp-project \
  --scope global \
  --target-https-proxy edge-proxy

# Or deploy to GCP while using GoDaddy for DNS-01 challenges
leet-ssl-cert init gcp \
  --dns-provider godaddy \
  --deployer gcp_lb \
  --project my-gcp-project \
  --scope global \
  --target-https-proxy edge-proxy
```

## Notes

- `gcp_lb` stores self-managed certificates in Compute Engine SSL certificate resources.
- Regional mode currently supports only `target_https_proxy`.
- If `project` is omitted from config, the tool falls back to `GCP_PROJECT`, `GOOGLE_CLOUD_PROJECT`, or the project discovered from ADC.
