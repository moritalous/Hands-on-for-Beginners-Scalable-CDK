from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elb
from aws_cdk import aws_rds as rds
from aws_cdk import core


class HandsOnForBeginnersScalableCdkStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        az1 = core.Fn.select(0, core.Fn.get_azs(region=core.Aws.REGION))
        az2 = core.Fn.select(1, core.Fn.get_azs(region=core.Aws.REGION))

        ##########
        # VPC
        ##########

        # VPC
        vpc = ec2.Vpc(self, "vpc", 
            cidr="10.0.0.0/16",
            subnet_configuration=[])
        
        # Internet gateway
        internet_gateway = ec2.CfnInternetGateway(self,"internet-gateway")
        ec2.CfnVPCGatewayAttachment(self, "internet_gateway_attatchment", 
            vpc_id=vpc.vpc_id, internet_gateway_id=internet_gateway.ref)

        # Public Subnet az1
        public_subnet_az1 = ec2.PublicSubnet(self, "subnet-public-1a",
            availability_zone=az1,
            cidr_block="10.0.0.0/24",
            vpc_id=vpc.vpc_id,
            map_public_ip_on_launch=True)

        public_subnet_az1.add_route("internet-gateway-route",
            router_id=internet_gateway.ref,
            router_type=ec2.RouterType.GATEWAY)

        # Public Subnet az2
        public_subnet_az2 = ec2.PublicSubnet(self, "subnet-public-1c",
            availability_zone=az2,
            cidr_block="10.0.1.0/24",
            vpc_id=vpc.vpc_id,
            map_public_ip_on_launch=True)

        public_subnet_az2.add_route("internet-gateway-route",
            router_id=internet_gateway.ref,
            router_type=ec2.RouterType.GATEWAY)

        # Private Subnet az1
        private_subnet_az1 = ec2.PrivateSubnet(self, "subnet-private-1a",
            availability_zone=az1,
            cidr_block="10.0.2.0/24",
            vpc_id=vpc.vpc_id)

        # Private Subnet az2
        private_subnet_az2 = ec2.PrivateSubnet(self, "subnet-private-1c",
            availability_zone=az2,
            cidr_block="10.0.3.0/24",
            vpc_id=vpc.vpc_id)

        ##########
        # EC2
        ##########

        # # EC2 Security Group
        ec2_security_group = ec2.SecurityGroup(self,"ec2-security-group",vpc=vpc)
        ec2_security_group.add_ingress_rule(peer=ec2.Peer.any_ipv4(),connection=ec2.Port.tcp(80))

        # User Data
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "yum -y update",
            "amazon-linux-extras install php7.2 -y",
            "yum -y install mysql httpd php-mbstring php-xml",

            "wget http://ja.wordpress.org/latest-ja.tar.gz -P /tmp/",
            "tar zxvf /tmp/latest-ja.tar.gz -C /tmp",
            "cp -r /tmp/wordpress/* /var/www/html/",
            "chown apache:apache -R /var/www/html",

            "systemctl enable httpd.service",
            "systemctl start httpd.service"
        )

        # EC2 Instance
        instance_az1 = ec2.CfnInstance(self, "wordpress-instance-az1", 
            subnet_id=public_subnet_az1.subnet_id,
            image_id=ec2.AmazonLinuxImage(generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2).get_image(self).image_id,
            instance_type=ec2.InstanceType.of(instance_class=ec2.InstanceClass.BURSTABLE3, instance_size=ec2.InstanceSize.MICRO).to_string(),
            security_group_ids=[ec2_security_group.security_group_id],
            user_data=core.Fn.base64(user_data.render())
            )
        
        core.CfnOutput(self, "EC2 PublicDnsName",value=instance_az1.attr_public_dns_name)

        ##########
        # RDS
        ##########

        # RDS Security Group
        rds_security_group = ec2.SecurityGroup(self,"rds-security-group",vpc=vpc)
        ec2.CfnSecurityGroupIngress(self, "rds-security-group-ingress", 
            group_id=rds_security_group.security_group_id,
            ip_protocol="tcp", 
            from_port=3306,
            to_port=3306,
            source_security_group_id=ec2_security_group.security_group_id)

        # RDS Subnet Group
        rds_subnet_group = rds.CfnDBSubnetGroup(self, "rds-subnet-group", 
            db_subnet_group_description="rds-subnet-group",
            subnet_ids=[private_subnet_az1.subnet_id, private_subnet_az2.subnet_id])
        
        # RDS Instance
        rds_instance = rds.CfnDBInstance(self, "rds-instance", 
            db_instance_identifier="wordpress-rds",
            engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_20).engine_type,
            db_instance_class="db.t3.micro",
            master_username="admin",
            master_user_password="password",
            db_name="wordpress",
            multi_az=False,
            vpc_security_groups=[rds_security_group.security_group_id],
            db_subnet_group_name=rds_subnet_group.ref,
            allocated_storage="20"
            )
        
        core.CfnOutput(self, "RDS EndpointAddress",value=rds_instance.attr_endpoint_address)
        core.CfnOutput(self, "RDS EndpointPort",value=rds_instance.attr_endpoint_port)

        ##########
        # ALB
        ##########

        # ALB Security Group
        alb_security_group = ec2.SecurityGroup(self,"alb-security-group",vpc=vpc)
        alb_security_group.add_ingress_rule(peer=ec2.Peer.any_ipv4(),connection=ec2.Port.tcp(80))

        # ALB Instance
        alb_instance = elb.ApplicationLoadBalancer(self, "alb", 
            vpc=vpc, 
            vpc_subnets=ec2.SubnetSelection(subnets=[public_subnet_az1, public_subnet_az2]),
            internet_facing=True,
            security_group=alb_security_group
            )

        # ALB Target Group
        alb_target_group = elb.ApplicationTargetGroup(self, "alb-target-group", 
            vpc=vpc,
            target_type=elb.TargetType.INSTANCE,
            targets=[elb.InstanceTarget(instance_az1.ref)],
            protocol=elb.ApplicationProtocol.HTTP,
            port=80,
            health_check=elb.HealthCheck(protocol=elb.ApplicationProtocol.HTTP, path="/wp-includes/images/blank.gif"))

        # ALB Listener
        alb_listener = elb.ApplicationListener(self, "alb-listener", 
            load_balancer=alb_instance, 
            default_target_groups=[alb_target_group], 
            protocol=elb.ApplicationProtocol.HTTP,
            port=80)

        core.CfnOutput(self, "ALB DNS Name",value=alb_instance.load_balancer_dns_name)
