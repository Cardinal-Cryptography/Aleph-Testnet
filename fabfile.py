'''Routines called by fab. Assumes that all are called from */experiments/aws.'''

from subprocess import call
from fabric import task
from os import remove

# ======================================================================================
#                                   setup
# ======================================================================================


@task
def setup(conn):
    conn.run('sudo apt update', hide='both')
    conn.run('sudo apt install -y zip unzip dtach', hide='both')


@task
def docker_setup(conn):
    conn.put('docker_setup.sh', '.')
    conn.run(
        'dtach -n `mktemp -u /tmp/dtach.XXXX` bash docker_setup.sh', hide='both')


@task
def send_data(conn, pid):
    ''' Sends keys and addresses. '''
    # sends all the keys, refactor to send only the needed one

    auth = pid_to_auth(pid)
    zip_file = f'data{pid}.zip'
    cmd = f'zip -r {zip_file} data/{auth}'
    with open('x', 'w') as f:
        f.write(cmd)
    call(cmd.split())
    conn.put(f'{zip_file}', '.')
    conn.run(f'unzip /home/ubuntu/{zip_file}')
    conn.put('chainspec.json', '.')


@task
def send_compose_config(conn):
    ''' Sends docker compose config file. '''
    conn.put('docker/docker-compose.yml', '.')


@task
def stop_services(conn):
    ''' Stops services defined in the compose file. '''
    conn.run('docker-compose -f docker-compose.yml down')


@task
def restart_services(conn):
    ''' Restarts services defined in the compose file. '''
    conn.run('docker-compose -f docker-compose.yml up -d')


@task
def update_node_image(conn):
    ''' Pulls a most recent version of the image. '''
    conn.run('docker pull public.ecr.aws/x2t8a1o3/aleph-node:latest')


@task
def get_logs(conn, pid):
    conn.run(f'zip {pid}.log.zip /home/ubuntu/{pid}.log')
    conn.get(f'/home/ubuntu/{pid}.log.zip', 'logs/')


@task
def run_docker_compose(conn, pid):
    authorities = ["Damian", "Tomasz", "Zbyszko",
                   "Hansu", "Adam", "Matt", "Antoni", "Michal"]
    pid = int(pid)
    auth = authorities[pid]
    bootnodes = []
    with open("data/addresses", "r") as f:
        addresses = [addr.strip() for addr in f.readlines()]
    with open("data/libp2p_public_keys", "r") as f:
        keys = [key.strip() for key in f.readlines()]
    for i, address in enumerate(addresses):
        bootnodes.append(
            f'/ip4/{address}/tcp/30334/p2p/{keys[i]}')
    bootnodes = " ".join(bootnodes)

    with open(f'env{pid}', 'a') as f:
        f.write(f'NODE_NAME={auth}\n')
        f.write('CHAIN_NAME=testnet1\n')
        f.write(f'BASE_PATH=/tmp/{auth}\n')
        f.write(f'NODE_KEY_PATH=/tmp/{auth}/libp2p_secret\n')
        f.write(f'BOOTNODES="{bootnodes}"\n')
    conn.put(f'env{pid}', '.')
    conn.run(f'sudo mv env{pid} /etc/environment')

    remove(f'env{pid}')

    conn.put('docker/docker-compose.yml', '.')

    conn.run(f'export NODE_NAME={auth} &&'
             'export CHAIN_NAME=testnet1 &&'
             f'export BASE_PATH=/tmp/{auth} &&'
             f'export NODE_KEY_PATH=/tmp/{auth}/libp2p_secret &&'
             f'export BOOTNODES="{bootnodes}" &&'
             'docker-compose -f docker-compose.yml up -d')


@task
def send_binary(conn):
    ''' Zips, sends and unzips the binary. '''
    zip_file = 'aleph-node.zip'
    cmd = f'zip -j {zip_file} bin/aleph-node'
    call(cmd.split())
    conn.put(f'{zip_file}', '.')
    conn.run(f'unzip -o /home/ubuntu/{zip_file} && rm {zip_file}')

# ======================================================================================
#                                       nginx
# ======================================================================================


@task
def run_nginx(conn):
    conn.run('sudo apt install -y nginx', hide='both')
    conn.put('nginx/default', '.')
    conn.run('sudo mv /home/ubuntu/default /etc/nginx/sites-available/')
    conn.put('nginx/cert/self-signed.crt', '.')
    conn.run('sudo mv /home/ubuntu/self-signed.crt /etc/nginx/')
    conn.put('nginx/cert/self-signed.key', '.')
    conn.run('sudo mv /home/ubuntu/self-signed.key /etc/nginx/')

    conn.run('sudo service nginx restart')
    conn.run('sudo service nginx status')

# ======================================================================================
#                                   run experiments
# ======================================================================================


def pid_to_auth(pid):
    with open('validator_accounts', 'r') as f:
        return f.readlines()[int(pid)][:-1]


@ task
def create_dispatch_cmd(conn,  pid):
    ''' Runs the protocol.'''

    auth = pid_to_auth(pid)
    n_bootnodes = 2
    with open("addresses", "r") as f:
        addrs = [f.readline().strip() for _ in range(n_bootnodes)]
    with open("libp2p_public_keys", "r") as f:
        keys = [f.readline().strip() for _ in range(n_bootnodes)]
    bootnodes = " ".join([
        f'/ip4/{addr}/tcp/30334/p2p/{key}' for addr, key in zip(addrs, keys)])

    cmd = f'/home/ubuntu/aleph-node '\
        '--validator '\
        '--chain chainspec.json '\
        f'--base-path data/{auth} '\
        '--rpc-port 9933 '\
        '--ws-port 9944 '\
        '--port 30334 '\
        '--execution Native '\
        '--no-prometheus '\
        '--no-telemetry '\
        f'--bootnodes {bootnodes} '\
        '--rpc-cors all '\
        '--rpc-methods Safe '\
        f'--node-key-file data/{auth}/p2p_secret '\
        f'2> {pid}.log'

    conn.run("echo > /home/ubuntu/cmd.sh")
    conn.run(f"sed -i '$a{cmd}' /home/ubuntu/cmd.sh")


@ task
def purge(conn, pid):
    auth = pid_to_auth(pid)
    conn.run(
        f'/home/ubuntu/aleph-node purge-chain --base-path data/{auth} --chain chainspec.json -y')


@ task
def dispatch(conn):
    conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` sh /home/ubuntu/cmd.sh')


@ task
def stop_world(conn):
    ''' Kills the committee member.'''
    conn.run('killall -9 aleph-node')

# ======================================================================================
#                                       testnet scenarios
# ======================================================================================


@task
def send_new_binary(conn):
    # 1. send new binary
    zip_file = 'aleph-node-new.zip'
    cmd = f'zip -j {zip_file} bin/aleph-node-new'
    call(cmd.split())
    conn.put(f'{zip_file}', '.')
    conn.run(f'unzip -o /home/ubuntu/{zip_file} && rm {zip_file}')

    # 2. make backups
    conn.run(
        'cp aleph-node aleph-node-old.backup && cp aleph-node-new aleph-node-new.backup')


@task
def upgrade_binary(conn):
    # 1. stop current binary
    conn.run('killall -9 aleph-node')

    # 2. replace binary with the new version
    conn.run('cp aleph-node aleph-node-old && cp aleph-node-new aleph-node')

    # 3. restart binary
    conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` sh /home/ubuntu/cmd.sh')


# ======================================================================================
#                                        misc
# ======================================================================================


@task
def send_chainspec(conn):
    conn.put('chainspec.json', '.')


@ task
def test(conn):
    ''' Tests if connection is ready '''

    conn.open()
