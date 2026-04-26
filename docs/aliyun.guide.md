# Alibaba Cloud (Aliyun) Provider Guide

This guide covers how to set up Alibaba Cloud credentials and configure `leet-ssl-cert` for Alibaba Cloud DNS and load balancer deployment.

## Credentials

`leet-ssl-cert` authenticates with Alibaba Cloud using an AccessKey pair.

### Where to Get Credentials

1. Log in to the [Alibaba Cloud Console](https://home.console.aliyun.com/)
2. Go to **AccessKey Management**: hover over your avatar in the top-right corner and select **AccessKey Management**, or visit https://ram.console.aliyun.com/manage/ak directly
3. Click **Create AccessKey** and save the `AccessKey ID` and `AccessKey Secret`

> **Recommended**: Create a RAM (Resource Access Management) sub-account with only the permissions you need instead of using your root account keys. See [RAM Users](https://ram.console.aliyun.com/users) in the console.

### Required Permissions

The AccessKey needs these permissions depending on which features you use:

| Feature | Required Policy |
|---|---|
| DNS (ACME challenges) | `AliyunDNSFullAccess` |
| CLB deployment | `AliyunSLBFullAccess` |
| ALB deployment | `AliyunALBFullAccess` and `AliyunYundunCertFullAccess` |

You can create a custom policy with narrower permissions if needed. The minimum actions required are:

- **DNS**: `alidns:AddDomainRecord`, `alidns:DeleteDomainRecord`, `alidns:DescribeDomainRecords`, `alidns:DescribeDomains`
- **CLB**: `slb:UploadServerCertificate`, `slb:DeleteServerCertificate`, `slb:DescribeServerCertificates`, `slb:SetLoadBalancerHTTPSListenerAttribute`, `slb:DescribeLoadBalancerHTTPSListenerAttribute`
- **ALB**: `alb:AssociateAdditionalCertificatesWithListener`, `alb:DissociateAdditionalCertificatesFromListener`, `alb:ListListeners`, `alb:ListListenerCertificates`, `cas:UploadUserCertificate`, `cas:DeleteUserCertificate`, `cas:ListUserCertificateOrder`

### Setting Credentials

Export the keys as environment variables:

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID=your-access-key-id
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=your-access-key-secret
```

The config file references them via `${VAR_NAME}` syntax:

```yaml
providers:
  aliyun:
    access_key_id: ${ALIBABA_CLOUD_ACCESS_KEY_ID}
    access_key_secret: ${ALIBABA_CLOUD_ACCESS_KEY_SECRET}
```

## DNS Provider

Set `dns_provider: aliyun` on a certificate entry. The tool automatically finds the matching DNS zone from your Alibaba Cloud DNS account.

No extra configuration is needed beyond the credentials above. The region is resolved from the deployer config or the `ALIBABA_CLOUD_REGION_ID` environment variable.

## Deployers

Alibaba Cloud has two load balancer products that `leet-ssl-cert` supports:

### CLB (Classic Load Balancer)

Formerly called **SLB** (Server Load Balancer). CLB is the original Alibaba Cloud load balancer. It works at Layer 4 (TCP/UDP) and Layer 7 (HTTP/HTTPS) with listener-based routing.

**Key concepts**:
- **Load Balancer ID** (`lb-xxxxxxxxx`): identifies the CLB instance
- **Listener Port**: the HTTPS listener port (typically `443`) where the certificate is bound
- Certificates are uploaded directly to the CLB service and bound per-listener

**How to find your CLB details**:
1. Go to the [CLB Console](https://slb.console.aliyun.com/)
2. Select your region
3. Find your CLB instance and copy the **Instance ID** (e.g., `lb-bp1abc...`)
4. Click the instance, go to the **Listeners** tab, and note the HTTPS listener port

**Config example**:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
    dns_provider: aliyun
    deploy:
      - provider: aliyun_clb
        region: cn-hangzhou
        load_balancer_id: lb-bp1xxxxxxxxxxxx
        listener_port: 443
```

| Field | Required | Description |
|---|---|---|
| `region` | Yes | Alibaba Cloud region (e.g., `cn-hangzhou`, `cn-beijing`, `us-west-1`) |
| `load_balancer_id` | Yes | CLB instance ID |
| `listener_port` | Yes | HTTPS listener port number |

### ALB (Application Load Balancer)

ALB is the newer Layer 7 load balancer with advanced routing, gRPC support, and more flexible certificate management.

**Key concepts**:
- **Listener ID** (`lsn-xxxxxxxxx`): identifies the HTTPS listener on the ALB
- Certificates are uploaded to the **Certificate Management Service (CAS)** and then associated with the ALB listener
- ALB supports multiple certificates on a single listener via SNI

**How to find your ALB details**:
1. Go to the [ALB Console](https://slb.console.aliyun.com/alb/)
2. Select your region
3. Find your ALB instance and click into it
4. Go to the **Listeners** tab and copy the **Listener ID** for the HTTPS listener

**Config example**:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
    dns_provider: aliyun
    deploy:
      - provider: aliyun_alb
        region: cn-hangzhou
        listener_id: lsn-bp1xxxxxxxxxxxx
```

| Field | Required | Description |
|---|---|---|
| `region` | Yes | Alibaba Cloud region |
| `listener_id` | Yes | ALB HTTPS listener ID |

## Region Codes

Common Alibaba Cloud regions:

| Region | Code |
|---|---|
| China (Hangzhou) | `cn-hangzhou` |
| China (Shanghai) | `cn-shanghai` |
| China (Beijing) | `cn-beijing` |
| China (Shenzhen) | `cn-shenzhen` |
| China (Hong Kong) | `cn-hongkong` |
| Singapore | `ap-southeast-1` |
| US (Virginia) | `us-east-1` |
| US (Silicon Valley) | `us-west-1` |

Full list: [Alibaba Cloud Regions and Zones](https://www.alibabacloud.com/help/en/ecs/product-overview/regions-and-zones)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install '.[aliyun]'
```
