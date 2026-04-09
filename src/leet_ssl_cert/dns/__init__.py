"""DNS provider registry."""

from .aliyun import AliyunDNSProvider
from .base import DNSProvider, get_dns_provider, register_dns_provider

register_dns_provider("aliyun", AliyunDNSProvider)

__all__ = ["DNSProvider", "AliyunDNSProvider", "get_dns_provider", "register_dns_provider"]
