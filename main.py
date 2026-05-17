from config import Config
from collectors import (
    vpcs, subnets, route_tables, internet_gateways, nat_gateways,
    transit_gateways, transit_gateway_attachments, security_groups,
    nacls, vpc_peerings, network_interfaces, vpc_endpoints,
    ec2, load_balancers, target_groups,
)


def main():
    config = Config()
    print("Jericho Extractor started")


if __name__ == "__main__":
    main()
