import boto3
import configparser
import sys
import os

EC2_CLIENT = None

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
        print("- please enter your AWS credentials:")
        aws_access_key_id = input("- AWS access key id: ").strip()
        aws_secret_access_key = input("- AWS secret access key: ").strip()
        aws_session_token = input("- AWS Session Token (press Enter if none): ").strip() or None
    
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
            aws_access_key_id = input("- AWS access key id: ").strip()
            aws_secret_access_key = input("- AWS secret access key: ").strip()
            aws_session_token = input("- AWS Session Token (press Enter if none): ").strip() or None
    
    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
    if aws_session_token:
        os.environ['AWS_SESSION_TOKEN'] = aws_session_token
    
    print('- AWS credentials verified')


def set_clients():
    print('- setting up boto3 client')
    try:
        global EC2_CLIENT
        EC2_CLIENT = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        print('- boto3 client ready')
    except Exception as e:
        print(f'- failed to set up boto3 client: {e}')
        sys.exit(1)


def get_vpc_id(vpc_name: str = 'polystudentlab-vpc'):
    """Find VPC by name"""
    try:
        response = EC2_CLIENT.describe_vpcs(
            Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}]
        )
        if response['Vpcs']:
            return response['Vpcs'][0]['VpcId']
        return None
    except Exception as e:
        print(f'- error finding VPC: {e}')
        return None


def terminate_instances(vpc_id: str):
    """Terminate all EC2 instances in the VPC"""
    print('\n- Terminating EC2 instances...')
    try:
        response = EC2_CLIENT.describe_instances(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']}
            ]
        )
        
        instance_ids = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_ids.append(instance['InstanceId'])
                print(f"  - Found instance: {instance['InstanceId']}")
        
        if instance_ids:
            EC2_CLIENT.terminate_instances(InstanceIds=instance_ids)
            print(f'  - Terminating {len(instance_ids)} instance(s)...')
            
            waiter = EC2_CLIENT.get_waiter('instance_terminated')
            waiter.wait(InstanceIds=instance_ids)
            print('  - All instances terminated')
        else:
            print('  - No instances to terminate')
            
    except Exception as e:
        print(f'  - Error terminating instances: {e}')


def delete_security_groups(vpc_id: str):
    """Delete all security groups in the VPC (except default)"""
    print('\n- Deleting security groups...')
    try:
        response = EC2_CLIENT.describe_security_groups(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        for sg in response['SecurityGroups']:
            if sg['GroupName'] != 'default':
                try:
                    EC2_CLIENT.delete_security_group(GroupId=sg['GroupId'])
                    print(f"  - Deleted security group: {sg['GroupName']} ({sg['GroupId']})")
                except Exception as e:
                    print(f"  - Could not delete {sg['GroupName']}: {e}")
    
    except Exception as e:
        print(f'  - Error deleting security groups: {e}')


def detach_and_delete_igw(vpc_id: str):
    """Detach and delete internet gateway"""
    print('\n- Deleting Internet Gateway...')
    try:
        response = EC2_CLIENT.describe_internet_gateways(
            Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
        )
        
        for igw in response['InternetGateways']:
            igw_id = igw['InternetGatewayId']
            EC2_CLIENT.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
            print(f'  - Detached IGW: {igw_id}')
            
            EC2_CLIENT.delete_internet_gateway(InternetGatewayId=igw_id)
            print(f'  - Deleted IGW: {igw_id}')
            
    except Exception as e:
        print(f'  - Error with Internet Gateway: {e}')


def delete_subnets(vpc_id: str):
    """Delete all subnets in the VPC"""
    print('\n- Deleting subnets...')
    try:
        response = EC2_CLIENT.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        for subnet in response['Subnets']:
            subnet_id = subnet['SubnetId']
            EC2_CLIENT.delete_subnet(SubnetId=subnet_id)
            print(f"  - Deleted subnet: {subnet_id}")
            
    except Exception as e:
        print(f'  - Error deleting subnets: {e}')


def delete_route_tables(vpc_id: str):
    """Delete all non-main route tables in the VPC"""
    print('\n- Deleting route tables...')
    try:
        response = EC2_CLIENT.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        for rt in response['RouteTables']:
            # Skip main route table
            is_main = any(assoc.get('Main', False) for assoc in rt.get('Associations', []))
            if not is_main:
                rt_id = rt['RouteTableId']
                EC2_CLIENT.delete_route_table(RouteTableId=rt_id)
                print(f'  - Deleted route table: {rt_id}')
                
    except Exception as e:
        print(f'  - Error deleting route tables: {e}')


def delete_vpc(vpc_id: str):
    """Delete the VPC"""
    print('\n- Deleting VPC...')
    try:
        EC2_CLIENT.delete_vpc(VpcId=vpc_id)
        print(f'  - Deleted VPC: {vpc_id}')
    except Exception as e:
        print(f'  - Error deleting VPC: {e}')


def main():
    print('='*70)
    print('AWS INFRASTRUCTURE CLEANUP SCRIPT')
    print('='*70)
    
    verify_aws_credentials()
    set_clients()
    
    vpc_name = 'polystudentlab-vpc'
    vpc_id = get_vpc_id(vpc_name)
    
    if not vpc_id:
        print(f'\n- VPC "{vpc_name}" not found. Nothing to clean up.')
        return
    
    print(f'\n- Found VPC: {vpc_id}')
    confirm = input(f'\n⚠️  Are you sure you want to delete VPC "{vpc_name}" and all its resources? (yes/no): ').strip().lower()
    
    if confirm != 'yes':
        print('- Cleanup cancelled')
        return
    
    print('\n' + '='*70)
    print('STARTING CLEANUP')
    print('='*70)
    
    # Order matters!
    terminate_instances(vpc_id)
    delete_security_groups(vpc_id)
    detach_and_delete_igw(vpc_id)
    delete_subnets(vpc_id)
    delete_route_tables(vpc_id)
    delete_vpc(vpc_id)
    
    print('\n' + '='*70)
    print('CLEANUP COMPLETE')
    print('='*70)


if __name__ == '__main__':
    main()