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
def send_data(conn):
    ''' Sends keys and addresses. '''
    # sends all the keys, refactor to send only the needed one

    conn.put('data.zip', '.')
    conn.run('unzip /home/ubuntu/data.zip')
    conn.run('cp -r /home/ubuntu/data/* /tmp')


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
    authorities = ["Damian", "Tomasz", "Zbyszko",
                   "Hansu", "Adam", "Matt", "Antoni", "Michal"]
    pid = int(pid)
    auth = authorities[pid]
    conn.run(f'zip {auth}.log.zip /home/ubuntu/{auth}-{pid}.log')
    conn.get(f'/home/ubuntu/{auth}.log.zip', './')


@task
def run_docker_compose(conn, pid):
    authorities = ["Damian", "Tomasz", "Zbyszko",
                   "Hansu", "Adam", "Matt", "Antoni", "Michal"]
    pid = int(pid)
    auth = authorities[pid]
    reserved_nodes = []
    with open("data/addresses", "r") as f:
        addresses = [addr.strip() for addr in f.readlines()]
    with open("data/libp2p_public_keys", "r") as f:
        keys = [key.strip() for key in f.readlines()]
    for i, address in enumerate(addresses):
        reserved_nodes.append(
            f'/ip4/{address}/tcp/30334/p2p/{keys[i]}')
    reserved_nodes = " ".join(reserved_nodes)

    with open(f'env{pid}', 'a') as f:
        f.write(f'NODE_NAME={auth}\n')
        f.write('CHAIN_NAME=testnet1\n')
        f.write(f'BASE_PATH=/tmp/{auth}\n')
        f.write(f'NODE_KEY_PATH=/tmp/{auth}/libp2p_secret\n')
        f.write(f'RESERVED_NODES="{reserved_nodes}"\n')
    conn.put(f'env{pid}', '.')
    conn.run(f'sudo mv env{pid} /etc/environment')

    remove(f'env{pid}')

    conn.put('docker/docker-compose.yml', '.')

    conn.run(f'export NODE_NAME={auth} &&'
             'export CHAIN_NAME=testnet1 &&'
             f'export BASE_PATH=/tmp/{auth} &&'
             f'export NODE_KEY_PATH=/tmp/{auth}/libp2p_secret &&'
             f'export RESERVED_NODES="{reserved_nodes}" &&'
             f'docker-compose -f docker-compose.yml up -d')


@task
def send_binary(conn):
    conn.put('bin/aleph-node', '.')

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
    return ["Damian", "Tomasz", "Zbyszko", "Hansu",
            "Adam", "Matt", "Antoni", "Michal"][int(pid)]


@task
def run_protocol(conn,  pid):
    ''' Runs the protocol.'''

    auth = pid_to_auth(pid)
    reserved_nodes = []
    with open("data/addresses", "r") as f:
        addresses = [addr.strip() for addr in f.readlines()]
    with open("data/libp2p_public_keys", "r") as f:
        keys = [key.strip() for key in f.readlines()]
    for i, address in enumerate(addresses):
        reserved_nodes.append(
            f'/ip4/{address}/tcp/30334/p2p/{keys[i]}')
    reserved_nodes = " ".join(reserved_nodes)

    conn.run(f'echo {len(addresses)} > /tmp/n_members')

    cmd = f'/home/ubuntu/aleph-node '\
        '--validator '\
        '--chain testnet1 '\
        f'--base-path /tmp/{auth} '\
        f'--name {auth} '\
        '--rpc-port 9933 '\
        '--ws-port 9944 '\
        '--port 30334 '\
        '--execution Native '\
        '--no-prometheus '\
        '--no-telemetry '\
        '--reserved-only '\
        f'--reserved-nodes {reserved_nodes} '\
        '--rpc-cors all '\
        '--rpc-methods Safe '\
        f'--node-key-file /tmp/{auth}/libp2p_secret '\
        '-lafa=debug '\
        '--session-period 500 ' \
        '--millisecs-per-block 1000 ' \
        '--pruning 432000 ' \
        '--unsafe-pruning ' \
        f'2> {auth}-{pid}.log'

    conn.run("echo > /home/ubuntu/cmd.sh")
    conn.run(f"sed -i '$a{cmd}' /home/ubuntu/cmd.sh")
    dispatch(conn)


@task
def purge(conn, pid):
    auth = pid_to_auth(pid)
    conn.run(
        f'/home/ubuntu/aleph-node purge-chain --base-path /tmp/{auth} --chain testnet1 -y')


@task
def dispatch(conn):
    conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` sh /home/ubuntu/cmd.sh')


N_REVERT = 10000


@task
def revert(conn, pid):
    auth = pid_to_auth(pid)
    conn.run(
        f'/home/ubuntu/aleph-node revert --base-path /tmp/{auth} --chain testnet1 {N_REVERT}')


@ task
def stop_world(conn):
    ''' Kills the committee member.'''

    conn.run('killall -9 aleph-node')

# ======================================================================================
#                                        misc
# ======================================================================================


@ task
def test(conn):
    ''' Tests if connection is ready '''

    conn.open()
