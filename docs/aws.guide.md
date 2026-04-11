# AWS Provider Guide

This guide covers how to set up AWS credentials and configure `leet-ssl-cert` for Route 53 DNS and AWS load balancer deployment.

## Credentials

`leet-ssl-cert` uses [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html), the standard AWS SDK. It supports the full boto3 credential chain, so you can authenticate in any way AWS allows.

### Where to Get Credentials

**IAM User (access keys)**:
1. Go to [IAM Console > Users](https://console.aws.amazon.com/iam/home#/users)
2. Select your user (or create one)
3. Go to **Security credentials** > **Access keys** > **Create access key**
4. Save the `Access Key ID` and `Secret Access Key`

> **Recommended**: Use an IAM user or role with only the permissions you need. Avoid using root account credentials.

### Required Permissions

| Feature | Suggested Managed Policy |
|---|---|
| DNS (ACME challenges) | `AmazonRoute53FullAccess` |
| ACM deployment | `AWSCertificateManagerFullAccess` |
| ELB/ALB deployment | `AWSCertificateManagerFullAccess` + `ElasticLoadBalancingFullAccess` |

Minimum IAM actions:

- **Route 53**: `route53:ListHostedZones`, `route53:ChangeResourceRecordSets`
- **ACM**: `acm:ImportCertificate`, `acm:DeleteCertificate`, `acm:ListCertificates`, `acm:ListTagsForCertificate`
- **ELBv2 (ALB/NLB)**: `elasticloadbalancing:DescribeListeners`, `elasticloadbalancing:ModifyListener`, `elasticloadbalancing:RemoveListenerCertificates`
- **Classic ELB**: `elasticloadbalancing:SetLoadBalancerListenerSSLCertificate`, `elasticloadbalancing:DescribeLoadBalancers`

### Setting Credentials

**Option 1 -- Environment variables** (simplest):

```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

**Option 2 -- AWS credentials file** (`~/.aws/credentials`):

```ini
[default]
aws_access_key_id = AKIA...
aws_secret_access_key = ...
```

**Option 3 -- Named profile**:

```ini
# ~/.aws/credentials
[leet-cert]
aws_access_key_id = AKIA...
aws_secret_access_key = ...
```

Then set `profile` in the config:

```yaml
providers:
  aws:
    profile: leet-cert
```

**Option 4 -- IAM role** (EC2 / ECS / Lambda):

No configuration needed. boto3 picks up the instance or task role automatically. Leave `providers.aws` empty:

```yaml
providers:
  aws: {}
```

## DNS Provider

Set `dns_provider: aws` on a certificate entry. The tool looks up the matching Route 53 hosted zone automatically.

Your domain must have a public hosted zone in Route 53. If your DNS is hosted elsewhere, use a different `dns_provider` (e.g., `aliyun`) while still deploying to AWS.

## Deployers

### ACM (AWS Certificate Manager)

`aws_acm` imports your certificate into ACM. This is useful when other AWS services (CloudFront, API Gateway, etc.) reference ACM certificates directly.

**Key concepts**:
- ACM stores certificates per-region
- Imported certificates (as opposed to ACM-issued ones) must be re-imported on renewal -- `leet-ssl-cert` handles this automatically
- CloudFront requires certificates in `us-east-1`

**Config example**:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
    dns_provider: aws
    deploy:
      - provider: aws_acm
        region: us-east-1
```

| Field | Required | Description |
|---|---|---|
| `region` | Yes | AWS region for the ACM certificate |

### ELB (Elastic Load Balancing)

`aws_elb` imports the certificate into ACM **and** binds it to a load balancer listener. It supports both modern (ALB/NLB via ELBv2) and Classic ELB.

**ALB / NLB (ELBv2)**:

**Key concepts**:
- **Listener ARN** (`arn:aws:elasticloadbalancing:...`): uniquely identifies an HTTPS listener
- The certificate is imported into ACM and then set as the default certificate on the listener

**How to find your Listener ARN**:
1. Go to [EC2 Console > Load Balancers](https://console.aws.amazon.com/ec2/home#LoadBalancers)
2. Select your ALB or NLB
3. Go to the **Listeners** tab
4. Copy the **Listener ARN** for port 443

**Config example**:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
    dns_provider: aws
    deploy:
      - provider: aws_elb
        region: us-east-1
        listener_arn: arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/my-alb/abc123/def456
```

| Field | Required | Description |
|---|---|---|
| `region` | Yes | AWS region |
| `listener_arn` | Yes | ARN of the HTTPS listener |

**Classic ELB**:

**Key concepts**:
- Classic ELB uses a **Load Balancer Name** (not an ARN) and a **Listener Port**
- This is the older ELB type; AWS recommends migrating to ALB/NLB for new deployments

**Config example**:

```yaml
certificates:
  - name: my-site
    domains:
      - example.com
    dns_provider: aws
    deploy:
      - provider: aws_elb
        region: us-east-1
        load_balancer_name: my-classic-lb
        listener_port: 443
```

| Field | Required | Description |
|---|---|---|
| `region` | Yes | AWS region |
| `load_balancer_name` | Yes | Classic ELB name |
| `listener_port` | No | HTTPS listener port (default: `443`) |

## Region Codes

Common AWS regions:

| Region | Code |
|---|---|
| US East (N. Virginia) | `us-east-1` |
| US East (Ohio) | `us-east-2` |
| US West (Oregon) | `us-west-2` |
| Europe (Ireland) | `eu-west-1` |
| Europe (Frankfurt) | `eu-central-1` |
| Asia Pacific (Tokyo) | `ap-northeast-1` |
| Asia Pacific (Singapore) | `ap-southeast-1` |
| Asia Pacific (Sydney) | `ap-southeast-2` |

Full list: [AWS Regions](https://docs.aws.amazon.com/general/latest/gr/rande.html)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install '.[aws]'
```
