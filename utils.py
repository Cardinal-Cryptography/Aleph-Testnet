'''Helper functions for shell'''

import json
import os
from pathlib import Path
from subprocess import call
from glob import glob

import boto3


def image_id_in_region(region_name, image_name='testnet1'):
    '''Find id of os image we use. The id may differ for different regions'''

    if image_name == 'ubuntu':
        image_name = 'ubuntu/images/hvm-ssd/ubuntu-hirsute-21.04-amd64-server-20210615'

    ec2 = boto3.resource('ec2', region_name)
    # in the below, there is only one image in the iterator
    for image in ec2.images.filter(Filters=[{'Name': 'name', 'Values': [image_name]}]):
        return image.id


def vpc_id_in_region(region_name):
    '''Find id of vpc in a given region. The id may differ for different regions'''

    ec2 = boto3.resource('ec2', region_name)
    vpcs_ids = []
    for vpc in ec2.vpcs.all():
        if vpc.is_default:
            vpcs_ids.append(vpc.id)

    if len(vpcs_ids) > 1 or not vpcs_ids:
        raise Exception(f'Found {len(vpcs_ids)} vpc, expected one!')

    return vpcs_ids[0]


def create_security_group(region_name, security_group_name):
    '''Creates security group that allows connecting via ssh and ports needed for sync'''

    ec2 = boto3.resource('ec2', region_name)

    # get the id of vpc in the given region
    vpc_id = vpc_id_in_region(region_name)
    sg = ec2.create_security_group(
        GroupName=security_group_name, Description='full sync', VpcId=vpc_id)

    # authorize incomming connections to port 22 for ssh, mainly for debugging
    # and to ports 9000, 10000, 11000, 12000 for syncing the dags
    sg.authorize_ingress(
        GroupName=security_group_name,
        IpPermissions=[
            {
                'FromPort': 0,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '178.128.198.123/32'}],
                'ToPort': 65535,
            },
            {
                'FromPort': 22,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 22,
            },
            {
                'FromPort': 9000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 9000,
            },
            {
                'FromPort': 10000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 10000,
            },
            {
                'FromPort': 11000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 11000,
            },
            {
                'FromPort': 12000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 12000,
            },
            {
                'FromPort': 13000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 13000,
            },
            {
                'FromPort': 14000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 14000,
            },
            {
                'FromPort': 15000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 15000,
            }
        ]
    )
    # authorize outgoing connections from ports 8000-20000 for intiating syncs
    sg.authorize_egress(
        IpPermissions=[
            {
                'FromPort': 8000,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 20000,
            }
        ]
    )

    return sg.id


def security_group_id_by_region(region_name, security_group_name='alephB'):
    '''Finds id of a security group. It may differ for different regions'''

    ec2 = boto3.resource('ec2', region_name)
    security_groups = ec2.security_groups.all()
    for security_group in security_groups:
        if security_group.group_name == security_group_name:
            return security_group.id

    # it seems that the group does not exist, let fix that
    return create_security_group(region_name, security_group_name)


def check_key_uploaded_all_regions(key_name='aleph'):
    '''Checks if in all regions there is public key corresponding to local private key.'''

    key_path = f'key_pairs/{key_name}.pem'
    assert os.path.exists(key_path), 'there is no key locally!'
    fingerprint_path = f'key_pairs/{key_name}.fingerprint'
    assert os.path.exists(
        fingerprint_path), 'there is no fingerprint of the key!'

    # read the fingerprint of the key
    with open(fingerprint_path, 'r') as f:
        fp = f.readline()

    for region_name in available_regions():
        ec2 = boto3.resource('ec2', region_name)
        # check if there is any key which fingerprint matches fp
        if not any(key.key_fingerprint == fp for key in ec2.key_pairs.all()):
            return False

    return True


def generate_key_pair_all_regions(key_name='aleph'):
    '''Generates key pair, stores private key locally, and sends public key to all regions'''

    key_path = f'key_pairs/{key_name}.pem'
    fingerprint_path = f'key_pairs/{key_name}.fingerprint'
    assert not os.path.exists(key_path), 'key exists, just use it!'

    if not os.path.exists('key_pairs'):
        os.mkdir('key_pairs')

    print('generating key pair')
    # generate a private key
    call(f'openssl genrsa -out {key_path} 2048'.split())
    # give the private key appropriate permissions
    call(f'chmod 400 {key_path}'.split())
    # generate a public key corresponding to the private key
    call(
        f'openssl rsa -in {key_path} -outform PEM -pubout -out {key_path}.pub'.split())
    # read the public key in a form needed by aws
    with open(key_path+'.pub', 'r') as f:
        pk_material = ''.join([line[:-1] for line in f.readlines()[1:-1]])

    # we need fingerprint of the public key in a form generated by aws, hence
    # we need to send it there at least once
    wrote_fp = False
    for region_name in use_regions():
        ec2 = boto3.resource('ec2', region_name)
        # first delete the old key
        for key in ec2.key_pairs.all():
            if key.name == key_name:
                print(f'deleting old key {key.name} in region', region_name)
                key.delete()
                break

        # send the public key to current region
        print('sending key pair to region', region_name)
        ec2.import_key_pair(KeyName=key_name, PublicKeyMaterial=pk_material)

        # write fingerprint
        if not wrote_fp:
            with open(fingerprint_path, 'w') as f:
                f.write(ec2.KeyPair(key_name).key_fingerprint)
            wrote_fp = True


def init_key_pair(region_name, key_name='aleph', dry_run=False):
    ''' Initializes key pair needed for using instances.'''

    key_path = f'key_pairs/{key_name}.pem'
    fingerprint_path = f'key_pairs/{key_name}.fingerprint'

    if os.path.exists(key_path) and os.path.exists(fingerprint_path):
        # we have the private key locally so let check if we have pk in the region

        if not dry_run:
            print('found local key; ', end='')
        ec2 = boto3.resource('ec2', region_name)
        with open(fingerprint_path, 'r') as f:
            fp = f.readline()

        keys = ec2.key_pairs.all()
        for key in keys:
            if key.name == key_name:
                if key.key_fingerprint != fp:
                    if not dry_run:
                        print('there is old version of key in region', region_name)
                    # there is an old version of the key, let remove it
                    key.delete()
                else:
                    if not dry_run:
                        print('local and upstream key match')
                    # check permissions
                    call(f'chmod 400 {key_path}'.split())
                    # everything is alright

                    return

        # for some reason there is no key up there, let send it
        with open(key_path+'.pub', 'r') as f:
            lines = f.readlines()
            pk_material = ''.join([line[:-1] for line in lines[1:-1]])
        ec2.import_key_pair(KeyName=key_name, PublicKeyMaterial=pk_material)
    else:
        # we don't have the private key, let create it
        generate_key_pair_all_regions(key_name)


def read_aws_keys():
    ''' Reads access and secret access keys needed for connecting to aws.'''

    creds_path = str(Path.joinpath(Path.home(), Path('.aws/credentials')))
    with open(creds_path, 'r') as f:
        f.readline()  # skip block description
        access_key_id = f.readline().strip().split('=')[-1].strip()
        secret_access_key = f.readline().strip().split('=')[-1].strip()

        return access_key_id, secret_access_key


def generate_keys():
    ''' Generate signing keys for the committee.'''
    # cmd = f'go run ../../../cmd/gomel-keys/main.go {n_parties} addresses'
    cmd = './bin/aleph-node dev-keys --base-path data --chain testnet1 --key-types aura alp0'
    call(cmd.split())

    cmd = 'cp /tmp/authorities_keys data'
    call(cmd.split())

    cmd = './p2p_keys/target/release/p2p_keys'
    call(cmd.split())


def write_addresses(ip_list):
    with open('data/addresses', 'w') as f:
        for ip in ip_list:
            f.write(ip+'\n')


def available_regions():
    ''' Returns a list of all currently available regions.'''
    non_badger_regions = list(
        set(boto3.Session().get_available_regions('ec2'))-set(badger_regions()))
    regions = badger_regions()+non_badger_regions
    for rn in ['ap-northeast-2', 'eu-west-3', 'eu-west-2', 'eu-north-1']:
        regions.remove(rn)

    return regions


def badger_regions():
    ''' Returns regions used by hbbft in theri experiments'''

    return ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1',
            'sa-east-1', 'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1']


def use_regions():
    return ['eu-central-1', 'eu-west-1', 'eu-west-2', 'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']


def default_region():
    ''' Helper function for getting default region name for current setup.'''

    return boto3.Session().region_name


def describe_instances(region_name):
    ''' Prints launch indexes and state of all instances in a given region.'''

    ec2 = boto3.resource('ec2', region_name)
    for instance in ec2.instances.all():
        print(
            f'ami_launch_index={instance.ami_launch_index} state={instance.state}')


def n_parties_per_regions(n_parties, regions=use_regions()):
    nhpr = {}
    n_left = n_parties
    for r in regions:
        nhpr[r] = n_parties // len(regions)
        n_left -= n_parties // len(regions)

    for i in range(n_left):
        nhpr[regions[i]] += 1

    for r in regions:
        if r in nhpr and not nhpr[r]:
            nhpr.pop(r)

    return nhpr


def translate_region_codes(regions):
    dictionary = {
        'us-east-1': 'Virginia,',
        'us-west-1': 'N. California,',
        'us-west-2': 'Oregon,',
        'eu-west-1': 'Ireland,',
        'eu-central-1': 'Frankfurt,',
        'ap-southeast-1': 'Singapore,',
        'ap-southeast-2': 'Sydney,',
        'ap-northeast-1': 'Tokyo,',
        'sa-east-1': 'Sao Paulo,',
    }
    return [dictionary[r] for r in regions]


def color_print(string):
    print('\x1b[6;30;42m' + string + '\x1b[0m')
