"""AWS provider plugin -- Route 53 DNS, ACM, and ELB."""

from leet_ssl_cert.providers import register_deployer, register_dns_provider
from leet_ssl_cert.providers.aws.acm import AWSACMDeployer
from leet_ssl_cert.providers.aws.dns import AWSRoute53DNSProvider
from leet_ssl_cert.providers.aws.elb import AWSELBDeployer

register_dns_provider("aws", AWSRoute53DNSProvider)
register_deployer("aws_acm", AWSACMDeployer)
register_deployer("aws_elb", AWSELBDeployer)
