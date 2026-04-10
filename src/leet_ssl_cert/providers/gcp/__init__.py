"""Google Cloud provider plugin -- Cloud DNS and HTTPS/SSL proxy deployment."""

from leet_ssl_cert.providers import register_deployer, register_dns_provider
from leet_ssl_cert.providers.gcp.dns import GCPCloudDNSProvider
from leet_ssl_cert.providers.gcp.lb import GCPLoadBalancerDeployer

register_dns_provider("gcp", GCPCloudDNSProvider)
register_deployer("gcp_lb", GCPLoadBalancerDeployer)
