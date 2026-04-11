"""GoDaddy provider plugin -- DNS only."""

from leet_ssl_cert.providers import register_dns_provider
from leet_ssl_cert.providers.godaddy.dns import GoDaddyDNSProvider

register_dns_provider("godaddy", GoDaddyDNSProvider)
