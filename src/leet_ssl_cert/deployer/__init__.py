"""Certificate deployer registry."""

from .aliyun_alb import AliyunALBDeployer
from .aliyun_clb import AliyunCLBDeployer
from .aws_acm import AWSACMDeployer
from .aws_elb import AWSELBDeployer
from .base import CertificateDeployer, get_deployer, register_deployer

register_deployer("aliyun_alb", AliyunALBDeployer)
register_deployer("aliyun_clb", AliyunCLBDeployer)
register_deployer("aws_acm", AWSACMDeployer)
register_deployer("aws_elb", AWSELBDeployer)

__all__ = [
    "CertificateDeployer",
    "AliyunALBDeployer",
    "AliyunCLBDeployer",
    "AWSACMDeployer",
    "AWSELBDeployer",
    "get_deployer",
    "register_deployer",
]
