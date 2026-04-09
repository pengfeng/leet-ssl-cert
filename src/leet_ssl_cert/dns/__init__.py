"""DNS provider registry."""

from .aliyun import AliyunDNSProvider
from .aws import AWSRoute53DNSProvider
from .base import DNSProvider, get_dns_provider, register_dns_provider
from .cloudflare import CloudflareDNSProvider

register_dns_provider("aliyun", AliyunDNSProvider)
register_dns_provider("aws", AWSRoute53DNSProvider)
register_dns_provider("cloudflare", CloudflareDNSProvider)

__all__ = [
    "DNSProvider",
    "AliyunDNSProvider",
    "AWSRoute53DNSProvider",
    "CloudflareDNSProvider",
    "get_dns_provider",
    "register_dns_provider",
]
