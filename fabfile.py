'''Routines called by fab. Assumes that all are called from */experiments/aws.'''

from fabric import task
from numpy import add

# ======================================================================================
#                                   setup
# ======================================================================================


@task
def mkdir(conn):
    conn.run('mkdir -p /home/ubuntu/testnet1/bin')
    conn.run('sudo apt install -y unzip')


@task
def send_data(conn, pid):
    ''' Sends keys and addresses. '''
    # sends all the keys, refactor to send only the needed one

    conn.put('data.zip', '/home/ubuntu/testnet1/')
    conn.run('unzip /home/ubuntu/testnet1/data.zip')
    conn.run('mv /home/ubuntu/data/* /tmp')


@task
def send_binary(conn):
    path = '/home/ubuntu/testnet1/bin/'
    conn.put('bin/aleph-node', path)


# ======================================================================================
#                                       nginx
# ======================================================================================


@task
def run_nginx(conn):
    conn.run('sudo apt install -y nginx')
    conn.put('nginx/default', '/home/ubuntu/')
    conn.run('sudo mv /home/ubuntu/default /etc/nginx/sites-available/')
    conn.put('nginx/cert/self-signed.crt', '/home/ubuntu/')
    conn.run('sudo mv /home/ubuntu/self-signed.crt /etc/nginx/')
    conn.put('nginx/cert/self-signed.key', '/home/ubuntu/')
    conn.run('sudo mv /home/ubuntu/self-signed.key /etc/nginx/')

    conn.run('sudo service nginx restart')
    conn.run('sudo service nginx status')


# ======================================================================================
#                                   run experiments
# ======================================================================================


@task
def run_protocol(conn, pid, delay='0'):
    ''' Runs the protocol.'''
    # conn.run('sudo apt update')
    # conn.run('sudo apt install -y dtach')

    path = '/home/ubuntu/testnet1'
    authorities = ["Damian", "Tomasz", "Zbyszko",
                   "Hansu", "Adam", "Matt", "Antoni", "Michal"]
    pid = int(pid)
    auth = authorities[pid]
    reserved_nodes = []
    with open("data/addresses", "r") as f:
        addresses = [addr.strip() for addr in f.readlines()]
    with open("data/libp2p2_public_keys", "r") as f:
        keys = [key.strip() for key in f.readlines()]
    for i, address in enumerate(addresses):
        reserved_nodes.append(
            f'/ip4/{address}/tcp/{30334+pid}/p2p/{keys[i]}')

    conn.run(f'echo {len(addresses)} > /tmp/n_members')
    # tmp fix
    conn.run(f'mkdir -p /tmp/{auth}/chains/a0tnet1/keystore')
    # conn.run(
    #     f'mv /tmp/{auth}/chains/testnet1/keystore/* /tmp/{auth}/chains/a0tnet1/keystore')

    reserved_nodes = " ".join(reserved_nodes)

    conn.run(
        f'/home/ubuntu/testnet1/bin/aleph-node purge-chain --base-path /tmp/{auth} --chain testnet1 -y')
    cmd = f'/home/ubuntu/testnet1/bin/aleph-node \
                --validator \
                --chain testnet1 \
                --base-path /tmp/{auth} \
                --name {auth} \
                --rpc-port {9933 + pid} \
                --ws-port {9944 + pid} \
                --port {30334 + pid} \
                --execution Native \
                --no-prometheus \
                --no-telemetry \
                --reserved-only \
                --reserved-nodes {reserved_nodes} \
                --rpc-cors all \
                --rpc-methods Safe \
                --node-key-file /tmp/{auth}/libp2p_secret \
                2> {auth}-{pid}.log'
    conn.run(f'echo {cmd} > /home/ubuntu/cmd.sh')
    conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` {cmd}')


@task
def stop_world(conn):
    ''' Kills the committee member.'''

    conn.run('killall -9 aleph-node')


# ======================================================================================
#                                        misc
# ======================================================================================


@task
def test(conn):
    ''' Tests if connection is ready '''

    conn.open()
