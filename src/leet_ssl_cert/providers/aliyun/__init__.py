"""Alibaba Cloud provider plugin -- DNS, CLB, and ALB."""

from leet_ssl_cert.providers import register_deployer, register_dns_provider
from leet_ssl_cert.providers.aliyun.alb import AliyunALBDeployer
from leet_ssl_cert.providers.aliyun.clb import AliyunCLBDeployer
from leet_ssl_cert.providers.aliyun.dns import AliyunDNSProvider

register_dns_provider("aliyun", AliyunDNSProvider)
register_deployer("aliyun_clb", AliyunCLBDeployer)
register_deployer("aliyun_alb", AliyunALBDeployer)
