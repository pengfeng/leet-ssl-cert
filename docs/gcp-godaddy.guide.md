# GCP Load Balancer + GoDaddy DNS Guide

This guide covers the mixed setup where your HTTPS load balancer is on Google Cloud and your public DNS zone is hosted on GoDaddy.

`leet-ssl-cert` handles two separate jobs in this topology:

- It creates and removes temporary `_acme-challenge` TXT records in GoDaddy for ACME DNS-01 validation.
- It uploads the issued certificate to Google Cloud and binds it to an existing target HTTPS proxy or target SSL proxy.

It does not create the load balancer, backend services, URL maps, forwarding rules, or your permanent A/AAAA/CNAME records.

## What You Need

### GoDaddy

- A GoDaddy account that owns the domain you want to validate.
- A production GoDaddy API key and secret.
- Access to the GoDaddy Management and DNS APIs for that account.
- Optional: a shopper ID if you are using reseller-style API calls that require `X-Shopper-Id`.

Export the credentials like this:

```bash
export GODADDY_API_KEY=your-production-key
export GODADDY_API_SECRET=your-production-secret
```

Optional reseller/testing variables:

```bash
export GODADDY_SHOPPER_ID=123456789
export GODADDY_API_BASE_URL=https://api.ote-godaddy.com
```

Use `GODADDY_API_BASE_URL` only if you intentionally want the OTE environment. For a real website, keep the default production API at `https://api.godaddy.com`.

### Google Cloud

- A Google Cloud project that contains the load balancer resources.
- Application Default Credentials for the account or service account running `leet-ssl-cert`.
- IAM permission to upload self-managed SSL certificates and update the target proxy.
- An existing GCP load balancer frontend that already points at a target HTTPS proxy or target SSL proxy.

Recommended environment variables:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=my-gcp-project
```

Recommended IAM role for this tool:

- `roles/compute.loadBalancerAdmin`

If you authenticate through workload identity or attached service accounts, you can omit `GOOGLE_APPLICATION_CREDENTIALS` as long as ADC resolves successfully.

## Install

GoDaddy DNS support is part of the base package. You only need the GCP extra for the deployment side:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install '.[gcp]'
```

## Setup Steps

### 1. Prepare the Google Cloud load balancer

Before you run `leet-ssl-cert`, the load balancer should already exist.

For the current `gcp_lb` deployer, that means one of these must already be present:

- A global `target_https_proxy`
- A regional `target_https_proxy`
- A global `target_ssl_proxy`

You will need the proxy name later. Example:

- `target_https_proxy: edge-proxy`
- `target_ssl_proxy: tcp-proxy`

### 2. Point your website DNS at the GCP load balancer

In GoDaddy DNS, create the normal website records for your site first:

- An `A` or `AAAA` record for apex domains such as `example.com`
- A `CNAME` or `A` record for hostnames such as `www.example.com`

These records should point to the external IP address or hostname exposed by your GCP load balancer frontend.

`leet-ssl-cert` will not manage these permanent website records. It only manages temporary ACME TXT records.

### 3. Generate the config

For a global HTTPS proxy:

```bash
leet-ssl-cert init gcp \
  --dns-provider godaddy \
  --deployer gcp_lb \
  --email admin@example.com \
  --name my-site \
  --domains example.com,www.example.com \
  --project my-gcp-project \
  --scope global \
  --target-https-proxy edge-proxy
```

For a regional HTTPS proxy, add `--scope regional --region us-central1`.

For a global SSL proxy, use `--target-ssl-proxy your-proxy-name` instead of `--target-https-proxy`.

### 4. Check the generated config

The important part is that DNS and deployment use different providers:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
      - www.example.com
    dns_provider: godaddy
    deploy:
      - provider: gcp_lb
        project: my-gcp-project
        scope: global
        target_https_proxy: edge-proxy

providers:
  godaddy:
    api_key: ${GODADDY_API_KEY}
    api_secret: ${GODADDY_API_SECRET}
  gcp:
    project: ${GOOGLE_CLOUD_PROJECT}
```

Optional GoDaddy settings you can add manually under `providers.godaddy`:

- `shopper_id`: only if your API flow requires `X-Shopper-Id`
- `api_base_url`: override the default production endpoint
- `ttl`: set a specific TTL for ACME TXT records

### 5. Issue and deploy

Run the full flow:

```bash
leet-ssl-cert run
```

Or separate the steps:

```bash
leet-ssl-cert issue
leet-ssl-cert deploy
```

During issuance, the tool will:

1. Find the matching GoDaddy zone for each requested domain.
2. Create temporary TXT records under `_acme-challenge`.
3. Wait for DNS propagation.
4. Finalize the ACME order.
5. Clean up the TXT records.
6. Upload the certificate to GCP.
7. Rebind the target proxy to the new certificate.

### 6. Verify HTTPS

After deployment:

- Open `https://example.com` in a browser.
- Check the certificate subject/SAN entries match your domains.
- Confirm the GCP target proxy now references the newly uploaded self-managed certificate.

For command-line verification:

```bash
openssl s_client -connect example.com:443 -servername example.com </dev/null
```

### 7. Automate renewal

Create a cron entry:

```bash
leet-ssl-cert cron
```

Then schedule `leet-ssl-cert run` on a host or job runner that has both:

- GoDaddy API credentials
- Google Cloud ADC credentials

## Notes

- The GoDaddy provider uses the Domains API with `Authorization: sso-key KEY:SECRET`.
- The tool defaults to the production GoDaddy API endpoint.
- `gcp_lb` stores self-managed certificates in Compute Engine SSL certificate resources, not Certificate Manager certificate maps.
- If your load balancer or proxy does not exist yet, create it first and then run this tool to keep the certificate current.

## Official References

- GoDaddy API getting started: <https://developer.godaddy.com/getstarted>
- GoDaddy Domains API docs: <https://developer.godaddy.com/doc/endpoint/domains>
- Google Cloud ADC: <https://cloud.google.com/docs/authentication/application-default-credentials>
- Google Cloud target proxies overview: <https://cloud.google.com/load-balancing/docs/target-proxies>
- Google Cloud external Application Load Balancer overview: <https://cloud.google.com/load-balancing/docs/https>
