import boto3
import configparser
import sys
import os
import time

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


def get_vpc_id(vpc_identifier: str):
    """Find VPC by ID or name"""
    try:
        if vpc_identifier.startswith('vpc-'):
            response = EC2_CLIENT.describe_vpcs(VpcIds=[vpc_identifier])
            if response['Vpcs']:
                return response['Vpcs'][0]['VpcId']
        
        response = EC2_CLIENT.describe_vpcs(
            Filters=[{'Name': 'tag:Name', 'Values': [vpc_identifier]}]
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
                instance_name = 'N/A'
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        instance_name = tag['Value']
                        break
                print(f"  - Found instance: {instance['InstanceId']} ({instance_name})")
        
        if instance_ids:
            EC2_CLIENT.terminate_instances(InstanceIds=instance_ids)
            print(f'  - Terminating {len(instance_ids)} instance(s)...')
            
            waiter = EC2_CLIENT.get_waiter('instance_terminated')
            print('  - Waiting for instances to terminate...')
            waiter.wait(InstanceIds=instance_ids)
            print('  - All instances terminated')
            
            print('  - Waiting for network interfaces to detach...')
            time.sleep(10)
        else:
            print('  - No instances to terminate')
            
    except Exception as e:
        print(f'Error terminating instances: {e}')


def delete_network_interfaces(vpc_id: str):
    """Delete all detached network interfaces in the VPC"""
    print('\n- Deleting network interfaces...')
    
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            response = EC2_CLIENT.describe_network_interfaces(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            if not response['NetworkInterfaces']:
                print('  - No network interfaces to delete')
                return
            
            deleted_count = 0
            for ni in response['NetworkInterfaces']:
                ni_id = ni['NetworkInterfaceId']
                
                if ni.get('Attachment'):
                    attachment_id = ni['Attachment'].get('AttachmentId')
                    if attachment_id:
                        try:
                            EC2_CLIENT.detach_network_interface(
                                AttachmentId=attachment_id,
                                Force=True
                            )
                            print(f"  - Detached network interface: {ni_id}")
                            time.sleep(2)
                        except Exception as e:
                            print(f"  - Could not detach {ni_id}: {e}")
                            continue
                
                try:
                    EC2_CLIENT.delete_network_interface(NetworkInterfaceId=ni_id)
                    print(f"  - Deleted network interface: {ni_id}")
                    deleted_count += 1
                except Exception as e:
                    if 'InvalidNetworkInterfaceID.NotFound' not in str(e):
                        print(f"  - Could not delete {ni_id}: {e}")
            
            if deleted_count == 0 and attempt < max_retries - 1:
                print(f'  - Waiting {retry_delay}s before retry...')
                time.sleep(retry_delay)
            elif deleted_count > 0:
                print(f'  - Deleted {deleted_count} network interface(s)')
                if attempt < max_retries - 1:
                    time.sleep(3)
                    
        except Exception as e:
            print(f'Error managing network interfaces: {e}')
            if attempt < max_retries - 1:
                time.sleep(retry_delay)


def delete_subnets(vpc_id: str):
    """Delete all subnets in the VPC"""
    print('\n- Deleting subnets...')
    
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            response = EC2_CLIENT.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            if not response['Subnets']:
                print('  - No subnets to delete')
                return
            
            deleted_count = 0
            remaining_subnets = []
            
            for subnet in response['Subnets']:
                subnet_id = subnet['SubnetId']
                subnet_name = 'N/A'
                for tag in subnet.get('Tags', []):
                    if tag['Key'] == 'Name':
                        subnet_name = tag['Value']
                        break
                
                try:
                    EC2_CLIENT.delete_subnet(SubnetId=subnet_id)
                    print(f"  - Deleted subnet: {subnet_id} ({subnet_name})")
                    deleted_count += 1
                except Exception as e:
                    if 'DependencyViolation' in str(e):
                        print(f"  - Subnet {subnet_id} ({subnet_name}) has dependencies, will retry")
                        remaining_subnets.append(subnet_id)
                    else:
                        print(f"  - Could not delete subnet {subnet_id}: {e}")
            
            if deleted_count > 0:
                print(f'  - Deleted {deleted_count} subnet(s)')
            
            if not remaining_subnets:
                print('  - All subnets deleted successfully')
                return
            
            if attempt < max_retries - 1:
                print(f'  - {len(remaining_subnets)} subnet(s) remaining, waiting {retry_delay}s...')
                time.sleep(retry_delay)
                
        except Exception as e:
            print(f'Error deleting subnets: {e}')
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    try:
        response = EC2_CLIENT.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        if response['Subnets']:
            print(f"  - Warning: {len(response['Subnets'])} subnet(s) could not be deleted")
    except:
        pass


def delete_route_tables(vpc_id: str):
    """Delete all non-main route tables in the VPC"""
    print('\n- Deleting route tables...')
    try:
        response = EC2_CLIENT.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        deleted_count = 0
        for rt in response['RouteTables']:
            is_main = any(assoc.get('Main', False) for assoc in rt.get('Associations', []))
            if not is_main:
                rt_id = rt['RouteTableId']
                rt_name = 'N/A'
                for tag in rt.get('Tags', []):
                    if tag['Key'] == 'Name':
                        rt_name = tag['Value']
                        break
                
                for assoc in rt.get('Associations', []):
                    if not assoc.get('Main', False):
                        try:
                            EC2_CLIENT.disassociate_route_table(
                                AssociationId=assoc['RouteTableAssociationId']
                            )
                            print(f"  - Disassociated route table {rt_id}")
                        except Exception as e:
                            print(f"  - Could not disassociate {rt_id}: {e}")
                
                try:
                    EC2_CLIENT.delete_route_table(RouteTableId=rt_id)
                    print(f'  - Deleted route table: {rt_id} ({rt_name})')
                    deleted_count += 1
                except Exception as e:
                    print(f"  - Could not delete route table {rt_id}: {e}")
        
        if deleted_count == 0:
            print('  - No custom route tables to delete')
        else:
            print(f'  - Deleted {deleted_count} route table(s)')
                
    except Exception as e:
        print(f'Error deleting route tables: {e}')


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
        
        if not response['InternetGateways']:
            print('  - No Internet Gateway to delete')
            
    except Exception as e:
        print(f'Error with Internet Gateway: {e}')


def delete_security_groups(vpc_id: str):
    """Delete all security groups in the VPC (except default)"""
    print('\n- Deleting security groups...')
    
    max_retries = 5
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            response = EC2_CLIENT.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            remaining_sgs = [sg for sg in response['SecurityGroups'] if sg['GroupName'] != 'default']
            
            if not remaining_sgs:
                print('  - All security groups deleted')
                return
            
            deleted_any = False
            for sg in remaining_sgs:
                try:
                    EC2_CLIENT.delete_security_group(GroupId=sg['GroupId'])
                    print(f"  - Deleted security group: {sg['GroupName']} ({sg['GroupId']})")
                    deleted_any = True
                except Exception as e:
                    if 'DependencyViolation' in str(e):
                        print(f"  - Skipping {sg['GroupName']} (has dependencies)")
                    else:
                        print(f"  - Could not delete {sg['GroupName']}: {e}")
            
            if deleted_any and attempt < max_retries - 1:
                print(f'  - Waiting {retry_delay}s before retry...')
                time.sleep(retry_delay)
        
        except Exception as e:
            print(f'Error deleting security groups: {e}')
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    response = EC2_CLIENT.describe_security_groups(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )
    remaining = [sg for sg in response['SecurityGroups'] if sg['GroupName'] != 'default']
    if remaining:
        print(f'  - Warning: {len(remaining)} security group(s) could not be deleted')


def main():
    print('='*70)
    print('AWS INFRASTRUCTURE CLEANUP SCRIPT')
    print('='*70)
    
    verify_aws_credentials()
    set_clients()
    
    vpc_identifier = 'vpc-0bdc139fd9ee529cc'
    vpc_id = get_vpc_id(vpc_identifier)
    
    if not vpc_id:
        print(f'\n- VPC "{vpc_identifier}" not found. Nothing to clean up.')
        return
    
    print(f'\n- Found VPC: {vpc_id}')
    
    print('\nThis will delete:')
    print('  - All EC2 instances')
    print('  - All network interfaces')
    print('  - All security groups (except default)')
    print('  - Internet gateways')
    print('  - All subnets')
    print('  - All custom route tables')
    
    confirm = input('\nAre you SURE you want to delete all resources? (type "yes" to confirm): ').strip()
    
    if confirm != 'yes':
        print('- Cleanup cancelled')
        return
    
    print('\n' + '='*70)
    print('STARTING CLEANUP')
    print('='*70)
    
    terminate_instances(vpc_id)
    delete_network_interfaces(vpc_id)
    delete_security_groups(vpc_id)
    detach_and_delete_igw(vpc_id)
    delete_route_tables(vpc_id)
    delete_subnets(vpc_id)
    
    print('\n' + '='*70)
    print('CLEANUP COMPLETE')
    print('='*70)
    print('\nNote: The VPC itself was NOT deleted (it may be managed by your lab)')


if __name__ == '__main__':
    main()