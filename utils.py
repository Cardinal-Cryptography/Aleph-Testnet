'''Helper functions for shell'''

import os
import json
from pathlib import Path
from subprocess import run

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


def create_security_group(region_name, ip_list=[], tag=''):
    '''Creates security group that allows connecting via ssh and ports needed for sync'''

    security_group_name = 'aleph-' + tag

    ec2 = boto3.resource('ec2', region_name)

    # get the id of vpc in the given region
    vpc_id = vpc_id_in_region(region_name)
    sg = ec2.create_security_group(
        GroupName=security_group_name, Description='full sync', VpcId=vpc_id)

    # authorize incomming connections to port 22 for ssh
    sg.authorize_ingress(
        GroupName=security_group_name,
        IpPermissions=[
            {
                'FromPort': 22,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'ToPort': 22,
            },
            {
                'FromPort': 0,
                'IpProtocol': '-1',
                'IpRanges': [{'CidrIp': f'{ip}/32'} for ip in ip_list],
                'ToPort': 65535,
            },
        ]
    )

    return sg


def allow_all_traffic_in_region(region_name, tag=''):
    security_group_name = 'aleph-' + tag

    ec2 = boto3.resource('ec2', region_name)

    for security_group in ec2.security_groups.all():
        if security_group.group_name != security_group_name:
            continue

        security_group.revoke_ingress(
            IpPermissions=security_group.ip_permissions)
        security_group.authorize_ingress(
            GroupName=security_group_name,
            IpPermissions=[
                {
                    'FromPort': 0,
                    'IpProtocol': '-1',
                    'IpRanges': [{'CidrIp': f'0.0.0.0/0'}],
                    'ToPort': 65535,
                },
            ]
        )

        return security_group


def update_security_group(region_name, ip_list=[], tag=''):
    '''Creates security group that allows connecting via ssh and ports needed for sync'''

    security_group_name = 'aleph-' + tag

    ec2 = boto3.resource('ec2', region_name)

    for security_group in ec2.security_groups.all():
        if security_group.group_name == security_group_name:
            security_group.revoke_ingress(
                IpPermissions=security_group.ip_permissions)

            # authorize incomming connections to port 22 for ssh and
            # all traffic from the given addresses
            security_group.authorize_ingress(
                GroupName=security_group_name,
                IpPermissions=[
                    {
                        'FromPort': 22,
                        'IpProtocol': 'tcp',
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                        'ToPort': 22,
                    },
                    {
                        'FromPort': 0,
                        'IpProtocol': '-1',
                        'IpRanges': [{'CidrIp': f'{ip}/32'} for ip in ip_list],
                        'ToPort': 65535,
                    },
                ]
            )

            return security_group


def security_group_id_by_region(region_name, tag=''):
    '''Finds id of a security group. It may differ for different regions'''

    security_group_name = 'aleph-' + tag

    ec2 = boto3.resource('ec2', region_name)
    security_groups = ec2.security_groups.all()
    for security_group in security_groups:
        if security_group.group_name == security_group_name:
            return security_group.id

    # it seems that the group does not exist, let fix that
    return create_security_group(region_name, tag=tag).id


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

    for region_name in use_regions():
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

    os.makedirs('key_pairs', exist_ok=True)

    print('generating key pair')
    # generate a private key
    run(f'openssl genrsa -out {key_path} 2048'.split())
    # give the private key appropriate permissions
    run(f'chmod 400 {key_path}'.split())
    # generate a public key corresponding to the private key
    run(
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
                    run(f'chmod 400 {key_path}'.split())
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


def generate_account():
    ''' Generate secret phrase and account id for a validator.'''
    cmd = './bin/aleph-node key generate --output-type json --words 24'
    jsons = run(cmd.split(), capture_output=True)
    creds = json.loads(jsons.stdout)
    phrase = creds['secretPhrase']
    account_id = creds['ss58PublicKey']

    return phrase, account_id


def generate_accounts(n_parties, chain, phrases_path, account_ids_path):
    ''' Generate secret phrases and account ids for the committee.'''

    if chain == 'dev':
        return [str(i) for i in range(n_parties)]

    phrases_account_ids = [generate_account() for _ in range(n_parties)]
    phrases, account_ids = list(zip(*phrases_account_ids))

    with open(phrases_path, 'w') as f:
        f.writelines([p+'\n' for p in phrases])

    with open(account_ids_path, 'w') as f:
        f.writelines([a+'\n' for a in account_ids])

    return account_ids


def bootstrap_chain(account_ids, chain):
    ''' Create the chain spec. '''

    cmd = './bin/aleph-node bootstrap-chain --base-path data'
    if chain == 'dev':
        cmd += f' --chain-id a0dnet1 --n-members {len(account_ids)}'
    else:
        cmd += ' --chain-id a0tnet1'\
            ' --chain-name AlephZeroTestnet'\
            f' --account-ids {",".join(account_ids)}'\
            ' --session-period 900'\
            ' --millisecs-per-block 1000'\
            ' --token-symbol TZERO'

    chainspec = run(cmd.split(), capture_output=True)
    chainspec = json.loads(chainspec.stdout)

    # TODO tmp workaround
    if chain != 'dev':
        chainspec['name'] = 'Aleph Zero Testnet'

    os.makedirs('accounts', exist_ok=True)

    sudo = generate_accounts(
        1, 'gen', 'accounts/sudo_sk', 'accounts/sudo_aid')[0]
    chainspec['genesis']['runtime']['sudo']['key'] = sudo
    chainspec['genesis']['runtime']['balances']['balances'].append(
        (sudo, 10**17))

    prepare_vesting(chainspec)

    with open('chainspec.json', 'w') as f:
        json.dump(chainspec, f, indent=4)


def prepare_vesting(chainspec):
    vested_accounts = generate_accounts(24, 'gen', 'accounts/vested_pharses',
                                        'accounts/vested_aids')
    balances = []
    vesting = []
    azero = 1000000000000
    hundred_azero = 100 * azero
    day = 86400
    for i, aid in enumerate(vested_accounts[:12]):
        mod = i+1
        balances.append((aid, hundred_azero))
        vesting.append((aid, mod, mod*day, mod*azero))

    month = 2592000
    for i, aid in enumerate(vested_accounts[12:]):
        mod = i+1
        balances.append((aid, 100*hundred_azero))
        vesting.append((aid, mod, mod*month, mod*hundred_azero))

    rtm = chainspec['genesis']['runtime']
    rtm['balances']['balances'] += balances
    rtm['vesting']['vesting'] = vesting


def generate_p2p_keys(account_ids):
    pks = ""
    for auth in account_ids:
        cmd = f'./bin/aleph-node key generate-node-key --file data/{auth}/p2p_secret'
        pk = run(cmd.split(), capture_output=True)
        pks += pk.stderr[:-1].decode() + '\n'

    with open('libp2p_public_keys', 'w') as f:
        f.write(pks)


def write_addresses(ip_list):
    with open('addresses', 'w') as f:
        for ip in ip_list:
            f.write(ip+'\n')


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


def testnet_regions():
    return ['eu-central-1', 'eu-west-1', 'eu-west-2', 'us-east-1', 'us-east-2']


def translate_region_codes(regions):
    dictionary = {
        'us-east-1': 'Virginia,',
        'us-east-2': 'Ohio,',
        'us-west-1': 'N. California,',
        'us-west-2': 'Oregon,',
        'eu-west-1': 'Ireland,',
        'eu-west-2': 'London,',
        'eu-central-1': 'Frankfurt,',
        'ap-southeast-1': 'Singapore,',
        'ap-southeast-2': 'Sydney,',
        'ap-northeast-1': 'Tokyo,',
        'sa-east-1': 'Sao Paulo,',
    }
    return [dictionary[r] for r in regions]


def color_print(string):
    print('\x1b[6;30;42m' + string + '\x1b[0m')


def fab_cmd():
    fabfile_path = os.environ.get('FABFILE_PATH')
    fabfile_path_flag = f'-r {fabfile_path}' if fabfile_path else ''
    return f'fab -i key_pairs/aleph.pem {fabfile_path_flag}'
