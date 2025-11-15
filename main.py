import boto3
import configparser
import sys
import os
from mypy_boto3_ec2 import EC2Client

EC2_CLIENT: EC2Client | None = None

"""
    Utility Methods
"""
def read_user_data(filename: str) -> str:
    global filepath
    try:
        filepath = os.path.join('user-data', filename)
        with open(filepath, 'r') as f:
            return f.read()

    except Exception:
        print(f'- error reading user data file {filepath}')
        sys.exit(1)


"""
    AWS SETUP
"""
def verify_aws_credentials():
    print('- verifying aws credentials')

    aws_access_key_id = None
    aws_secret_access_key = None
    aws_session_token = None
    is_not_valid = True

    credentials_path = os.path.expanduser('~/.aws/credentials')
    config = configparser.ConfigParser()

    if os.path.exists(credentials_path):
        config.read(credentials_path)
        if 'default' in config:
            aws_access_key_id = config['default'].get('aws_access_key_id')
            aws_secret_access_key = config['default'].get('aws_secret_access_key')
            aws_session_token = config['default'].get('aws_session_token')

    if not aws_access_key_id or not aws_secret_access_key:
        aws_access_key_id, aws_secret_access_key, aws_session_token = get_user_credentials()

    while is_not_valid:
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_session_token=aws_session_token
            )

            sts.get_caller_identity()
            is_not_valid = False

        except Exception:
            print('- credential verification failed')
            print('- please try again.\n')
            aws_access_key_id, aws_secret_access_key, aws_session_token = get_user_credentials()

    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
    if aws_session_token:
        os.environ['AWS_SESSION_TOKEN'] = aws_session_token

    print('- AWS credentials verified')


def get_user_credentials() -> tuple[str, str, str | None]:
    print("- please enter your AWS credentials:")
    aws_access_key_id = input("- AWS access key id: ").strip()
    aws_secret_access_key = input("- AWS secret access key: ").strip()
    aws_session_token = input("- AWS Session Token (press Enter if none): ").strip() or None
    return aws_access_key_id, aws_secret_access_key, aws_session_token


def set_clients():
    print('- starting setting up the boto3 clients')
    try:
        global EC2_CLIENT
        EC2_CLIENT = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        print('- finished setting up the boto3 clients')
    except Exception:
        print('- failed to set the boto3 clients')
        sys.exit(1)

"""
    INFRA
"""
def get_vpc(vpc_id: str) -> str:
    print(f'- retrieving VPC {vpc_id}')
    try:
        response = EC2_CLIENT.describe_vpcs(
            VpcIds=[vpc_id]
        )
        
        if response['Vpcs']:
            vpc = response['Vpcs'][0]
            vpc_id = vpc['VpcId']
            cidr_block = vpc['CidrBlock']
            print(f'- found VPC: {vpc_id} with CIDR {cidr_block}')
            
            EC2_CLIENT.modify_vpc_attribute(
                VpcId=vpc_id,
                EnableDnsHostnames={'Value': True}
            )
            
            EC2_CLIENT.modify_vpc_attribute(
                VpcId=vpc_id,
                EnableDnsSupport={'Value': True}
            )
            
            print(f'- VPC {vpc_id} configured successfully')
            return vpc_id
        else:
            print(f'- VPC {vpc_id} not found')
            sys.exit(1)
            
    except Exception as e:
        print(f'- error retrieving VPC: {e}')
        sys.exit(1)


def create_subnet(vpc_id: str, cidr_block: str, availability_zone: str, subnet_name: str, is_public: bool = False) -> str:
    print(f'- creating subnet {subnet_name} with CIDR {cidr_block} in {availability_zone}')
    try:
        response = EC2_CLIENT.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr_block,
            AvailabilityZone=availability_zone,
            TagSpecifications=[
                {
                    'ResourceType': 'subnet',
                    'Tags': [
                        {'Key': 'Name', 'Value': subnet_name},
                        {'Key': 'Type', 'Value': 'Public' if is_public else 'Private'}
                    ]
                }
            ]
        )
        
        subnet_id = response['Subnet']['SubnetId']
        print(f'- created subnet: {subnet_id}')
        
        if is_public:
            EC2_CLIENT.modify_subnet_attribute(
                SubnetId=subnet_id,
                MapPublicIpOnLaunch={'Value': True}
            )
            print(f'- enabled auto-assign public IP for {subnet_name}')
        
        return subnet_id
        
    except Exception as e:
        print(f'- error creating subnet {subnet_name}: {e}')
        sys.exit(1)


def create_all_subnets(vpc_id: str, region: str = 'us-east-1') -> dict:
    print('\n- creating all subnets')
    
    subnets = {}
    
    # AZ1 (us-east-1a)
    subnets['public_az1'] = create_subnet(
        vpc_id=vpc_id,
        cidr_block='10.0.0.0/24',
        availability_zone=f'{region}a',
        subnet_name='polystudentlab-public-az1',
        is_public=True
    )
    
    subnets['private_az1'] = create_subnet(
        vpc_id=vpc_id,
        cidr_block='10.0.128.0/24',
        availability_zone=f'{region}a',
        subnet_name='polystudentlab-private-az1',
        is_public=False
    )
    
    # AZ2 (us-east-1b)
    subnets['public_az2'] = create_subnet(
        vpc_id=vpc_id,
        cidr_block='10.0.16.0/24',
        availability_zone=f'{region}b',
        subnet_name='polystudentlab-public-az2',
        is_public=True
    )
    
    subnets['private_az2'] = create_subnet(
        vpc_id=vpc_id,
        cidr_block='10.0.144.0/24',
        availability_zone=f'{region}b',
        subnet_name='polystudentlab-private-az2',
        is_public=False
    )
    
    print('- all subnets created successfully')
    print(f'  - Public AZ1: {subnets["public_az1"]}')
    print(f'  - Private AZ1: {subnets["private_az1"]}')
    print(f'  - Public AZ2: {subnets["public_az2"]}')
    print(f'  - Private AZ2: {subnets["private_az2"]}')
    
    return subnets


def create_internet_gateway(vpc_id: str, igw_name: str = 'polystudentlab-igw') -> str:
    print(f'\n- creating Internet Gateway {igw_name}')
    try:
        response = EC2_CLIENT.create_internet_gateway(
            TagSpecifications=[
                {
                    'ResourceType': 'internet-gateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': igw_name}
                    ]
                }
            ]
        )
        
        igw_id = response['InternetGateway']['InternetGatewayId']
        print(f'- created Internet Gateway: {igw_id}')
        
        EC2_CLIENT.attach_internet_gateway(
            InternetGatewayId=igw_id,
            VpcId=vpc_id
        )
        print(f'- attached Internet Gateway {igw_id} to VPC {vpc_id}')
        
        return igw_id
        
    except Exception as e:
        print(f'- error creating/attaching Internet Gateway: {e}')
        sys.exit(1)


def create_route_table(vpc_id: str, rt_name: str, igw_id: str = None) -> str:
    print(f'\n- creating route table {rt_name}')
    try:
        response = EC2_CLIENT.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'route-table',
                    'Tags': [
                        {'Key': 'Name', 'Value': rt_name}
                    ]
                }
            ]
        )
        
        rt_id = response['RouteTable']['RouteTableId']
        print(f'- created route table: {rt_id}')
        
        if igw_id:
            EC2_CLIENT.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=igw_id
            )
            print(f'- added route 0.0.0.0/0 -> {igw_id} to route table {rt_id}')
        
        return rt_id
        
    except Exception as e:
        print(f'- error creating route table: {e}')
        sys.exit(1)


def associate_route_table(rt_id: str, subnet_id: str, subnet_name: str = '') -> str:
    print(f'- associating route table {rt_id} with subnet {subnet_name or subnet_id}')
    try:
        response = EC2_CLIENT.associate_route_table(
            RouteTableId=rt_id,
            SubnetId=subnet_id
        )
        
        association_id = response['AssociationId']
        print('- successfully associated route table with subnet')
        return association_id
        
    except Exception as e:
        print(f'- error associating route table with subnet: {e}')
        sys.exit(1)


def configure_route_tables(vpc_id: str, igw_id: str, subnets: dict) -> dict:
    print('\n- configuring route tables')
    
    route_tables = {}
    
    public_rt_id = create_route_table(
        vpc_id=vpc_id,
        rt_name='polystudentlab-public-rt',
        igw_id=igw_id
    )
    route_tables['public'] = public_rt_id
    
    associate_route_table(public_rt_id, subnets['public_az1'], 'public-az1')
    associate_route_table(public_rt_id, subnets['public_az2'], 'public-az2')
    
    private_rt_id = create_route_table(
        vpc_id=vpc_id,
        rt_name='polystudentlab-private-rt',
        igw_id=None
    )
    route_tables['private'] = private_rt_id
    
    associate_route_table(private_rt_id, subnets['private_az1'], 'private-az1')
    associate_route_table(private_rt_id, subnets['private_az2'], 'private-az2')
    
    print('- route tables configured successfully')
    print(f'  - Public RT: {public_rt_id} (with internet access)')
    print(f'  - Private RT: {private_rt_id} (no internet access)')
    
    return route_tables


def create_app_security_group(vpc_id: str, sg_name: str = 'polystudentlab-app-sg') -> str:
    print(f'\n- creating App server security group {sg_name}')
    
    try:
        response = EC2_CLIENT.create_security_group(
            GroupName=sg_name,
            Description='Security group for App servers - allows SSH, HTTP, HTTPS, OSSEC, and Elasticsearch',
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'Type', 'Value': 'App-Server'}
                    ]
                }
            ]
        )
        
        sg_id = response['GroupId']
        print(f'- created App security group: {sg_id}')
        
        ingress_rules = [
            {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'CidrIp': '0.0.0.0/0', 'Description': 'SSH'},
            {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'CidrIp': '0.0.0.0/0', 'Description': 'HTTP'},
            {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS'},
            {'IpProtocol': 'tcp', 'FromPort': 1514, 'ToPort': 1514, 'CidrIp': '0.0.0.0/0', 'Description': 'OSSEC'},
            {'IpProtocol': 'tcp', 'FromPort': 9200, 'ToPort': 9300, 'CidrIp': '0.0.0.0/0', 'Description': 'Elasticsearch'},
        ]
        
        for rule in ingress_rules:
            EC2_CLIENT.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    'IpProtocol': rule['IpProtocol'],
                    'FromPort': rule['FromPort'],
                    'ToPort': rule['ToPort'],
                    'IpRanges': [{'CidrIp': rule['CidrIp'], 'Description': rule['Description']}]
                }]
            )
            print(f'- added ingress rule: {rule["Description"]} ({rule["IpProtocol"]} port {rule["FromPort"]}-{rule["ToPort"]})')
        
        print(f'- App security group {sg_name} configured successfully')
        
        return sg_id
        
    except Exception as e:
        print(f'- error creating App security group: {e}')
        sys.exit(1)


def create_db_security_group(vpc_id: str, app_sg_id: str, sg_name: str = 'polystudentlab-db-sg') -> str:
    print(f'\n- creating DB server security group {sg_name}')
    
    try:
        response = EC2_CLIENT.create_security_group(
            GroupName=sg_name,
            Description='Security group for DB servers - only accessible from App servers',
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'Type', 'Value': 'DB-Server'}
                    ]
                }
            ]
        )
        
        sg_id = response['GroupId']
        print(f'- created DB security group: {sg_id}')
        
        ingress_rules = [
            {'IpProtocol': 'tcp', 'FromPort': 3306, 'ToPort': 3306, 'Description': 'MySQL from App servers'},
            {'IpProtocol': 'tcp', 'FromPort': 1433, 'ToPort': 1433, 'Description': 'MSSQL from App servers'},
            {'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432, 'Description': 'PostgreSQL from App servers'},
            {'IpProtocol': 'tcp', 'FromPort': 3389, 'ToPort': 3389, 'Description': 'RDP from App servers'},
            {'IpProtocol': 'tcp', 'FromPort': 1514, 'ToPort': 1514, 'Description': 'OSSEC from App servers'},
        ]
        
        for rule in ingress_rules:
            EC2_CLIENT.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    'IpProtocol': rule['IpProtocol'],
                    'FromPort': rule['FromPort'],
                    'ToPort': rule['ToPort'],
                    'UserIdGroupPairs': [{'GroupId': app_sg_id, 'Description': rule['Description']}]
                }]
            )
            print(f'- added ingress rule: {rule["Description"]} ({rule["IpProtocol"]} port {rule["FromPort"]}-{rule["ToPort"]})')
        
        print(f'- DB security group {sg_name} configured successfully')
        print('- DB servers are ONLY accessible from App servers')
        
        return sg_id
        
    except Exception as e:
        print(f'- error creating DB security group: {e}')
        sys.exit(1)


def create_security_groups(vpc_id: str) -> dict:
    print('\n- Creating Security groups')
    
    security_groups = {}
    
    app_sg_id = create_app_security_group(vpc_id)
    security_groups['app'] = app_sg_id
    
    db_sg_id = create_db_security_group(vpc_id, app_sg_id)
    security_groups['db'] = db_sg_id
    
    print('\n- Security groups created successfully:')
    print(f'  - App SG: {app_sg_id} (public access)')
    print(f'  - DB SG: {db_sg_id} (only accessible from App servers)')
    
    return security_groups


def create_app_server(instance_name: str, subnet_id: str, security_group_id: str, ami_id: str, key_name: str = 'polystudent-keypair', iam_profile: str = 'LabInstanceProfile') -> str:
    print(f'\n- creating App server instance: {instance_name}')
    
    try:
        user_data = read_user_data('app-server.tpl')
        
        response = EC2_CLIENT.run_instances(
            ImageId=ami_id,
            InstanceType='t2.micro',
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            SubnetId=subnet_id,
            UserData=user_data,
            IamInstanceProfile={'Name': iam_profile},
            BlockDeviceMappings=[
                {
                    'DeviceName': '/dev/sda1',
                    'Ebs': {
                        'VolumeSize': 80,
                        'VolumeType': 'gp3',
                        'DeleteOnTermination': True
                    }
                }
            ],
            Monitoring={'Enabled': True},
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': instance_name},
                        {'Key': 'Type', 'Value': 'App-Server'}
                    ]
                }
            ],
            MinCount=1,
            MaxCount=1
        )
        
        instance_id = response['Instances'][0]['InstanceId']
        print(f'- created App server instance: {instance_id}')
        print('- waiting for instance to be running...')
        
        waiter = EC2_CLIENT.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        print(f'- App server {instance_name} is now running')
        return instance_id
        
    except Exception as e:
        print(f'- error creating App server: {e}')
        sys.exit(1)


def create_db_server(instance_name: str, subnet_id: str, security_group_id: str, ami_id: str, key_name: str = 'polystudent-keypair', iam_profile: str = 'LabInstanceProfile') -> str:
    print(f'\n- creating DB server instance: {instance_name}')
    
    try:
        user_data = read_user_data('db-server.tpl')
        
        response = EC2_CLIENT.run_instances(
            ImageId=ami_id,
            InstanceType='t2.micro',
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            SubnetId=subnet_id,
            UserData=user_data,
            IamInstanceProfile={'Name': iam_profile},
            BlockDeviceMappings=[
                {
                    'DeviceName': '/dev/sda1',
                    'Ebs': {
                        'VolumeSize': 30,
                        'VolumeType': 'gp3',
                        'DeleteOnTermination': True
                    }
                }
            ],
            Monitoring={'Enabled': True},
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': instance_name},
                        {'Key': 'Type', 'Value': 'DB-Server'}
                    ]
                }
            ],
            MinCount=1,
            MaxCount=1
        )
        
        instance_id = response['Instances'][0]['InstanceId']
        print(f'- created DB server instance: {instance_id}')
        print('- waiting for instance to be running...')
        
        waiter = EC2_CLIENT.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        print(f'- DB server {instance_name} is now running')
        return instance_id
        
    except Exception as e:
        print(f'- error creating DB server: {e}')
        sys.exit(1)


def create_all_instances(subnets: dict, security_groups: dict, ubuntu_ami: str= 'ami-0ecb62995f68bb549', windows_ami: str= 'ami-0b4bc1e90f30ca1ec') -> dict:
    
    instances = {}
    
    print('\n- [3.1.1] Creating App Server for AZ2...')
    instances['app_az2'] = create_app_server(
        instance_name='polystudent-app-az2',
        subnet_id=subnets['public_az2'],
        security_group_id=security_groups['app'],
        ami_id=ubuntu_ami
    )
    
    print('\n- [3.1.2] Creating DB Server for AZ1...')
    instances['db_az1'] = create_db_server(
        instance_name='polystudent-db-az1',
        subnet_id=subnets['private_az1'],
        security_group_id=security_groups['db'],
        ami_id=windows_ami
    )
    
    print('\n[3.1.2] Creating DB Server for AZ2...')
    instances['db_az2'] = create_db_server(
        instance_name='polystudent-db-az2',
        subnet_id=subnets['private_az2'],
        security_group_id=security_groups['db'],
        ami_id=windows_ami
    )
    

    print(f"- App AZ2: {instances['app_az2']}")
    print(f"- DB AZ1: {instances['db_az1']}")
    print(f"- DB AZ2: {instances['db_az2']}")
    
    return instances


def main():
    print('*'*26 + ' BEGINNING AWS SETUP ' + '*'*26)
    verify_aws_credentials()
    set_clients()
    print('*'*26 + '*********************' + '*'*26)
    print('')
    print('*'*26 + ' INFRASTRUCTURE START ' + '*'*26)
    
    vpc_id = get_vpc('vpc-0bdc139fd9ee529cc')
    subnets = create_all_subnets(vpc_id)
    igw_id = create_internet_gateway(vpc_id)
    configure_route_tables(vpc_id, igw_id, subnets)
    security_groups = create_security_groups(vpc_id)
    
    # Question 3.1
    create_all_instances(subnets, security_groups)
    
    print('*'*26 + '*********************' + '*'*26)


if __name__ == '__main__':
    main()

