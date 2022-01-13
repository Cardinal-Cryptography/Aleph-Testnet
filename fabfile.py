'''Routines called by fab. Assumes that all are called from */experiments/aws.'''
import json
from itertools import chain
from os import remove
from subprocess import call

from fabric import task


# ======================================================================================
#                                   setup
# ======================================================================================


@task
def setup(conn):
    conn.run('sudo apt update', hide='both')
    conn.run('sudo apt install -y zip unzip dtach', hide='both')
    conn.run('sudo sh -c "echo core >/proc/sys/kernel/core_pattern"', hide='both')


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
    conn.run(f'cp /home/ubuntu/{pid}.log node{pid}.log')
    conn.run(f'zip {pid}.log.zip node{pid}.log')
    conn.run(f'rm node{pid}.log')
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


@task
def create_dispatch_cmd(conn, pid):
    ''' Runs the protocol.'''

    auth = pid_to_auth(pid)
    reserved_nodes = []
    with open("addresses", "r") as f:
        addresses = [addr.strip() for addr in f.readlines()]
    with open("libp2p_public_keys", "r") as f:
        keys = [key.strip() for key in f.readlines()]
    for i, address in enumerate(addresses):
        reserved_nodes.append(
            f'/ip4/{address}/tcp/30334/p2p/{keys[i]}')
    reserved_nodes = " ".join(reserved_nodes)

    no_val_flags = [
        '--validator',
        '--prometheus-external',
        '--no-telemetry',
        '--unsafe-ws-external',
    ]
    debug_flags = [
        '-lafa=debug',
        '-lAlephBFT-creator=trace',
    ]
    val_flags = {
        '--chain': 'chainspec.json',
        '--base-path': f'data/{auth}',
        '--rpc-port': '9933',
        '--ws-port': '9944',
        '--port': '30334',
        '--execution': 'Native',
        '--prometheus-port': '9615',
        '--rpc-cors': 'all',
        '--rpc-methods': 'Safe',
        '--node-key-file': f'data/{auth}/p2p_secret',
        '--reserved-nodes': reserved_nodes,
    }

    with open('node_flags.json', 'r') as f:
        custom_val_flags = json.load(f)

    val_flags.update(custom_val_flags)
    val_flags = [f'{key} {val}' for (key, val) in val_flags.items()]

    flags = " ".join(chain(no_val_flags, val_flags, debug_flags))
    cmd = f'/home/ubuntu/aleph-node {flags} 2> {pid}.log'

    conn.run("echo > /home/ubuntu/cmd.sh")
    conn.run(f"sed -i '$a{cmd}' /home/ubuntu/cmd.sh")


@task
def purge(conn, pid):
    auth = pid_to_auth(pid)
    conn.run(
        f'/home/ubuntu/aleph-node purge-chain --base-path data/{auth} --chain chainspec.json -y')


@task
def dispatch(conn):
    run_node_exporter_cmd = f'./node_exporter-*.*-amd64/node_exporter'
    conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` {run_node_exporter_cmd}')
    conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` sh /home/ubuntu/cmd.sh')


@task
def install_prometheus_exporter(conn):
    install_cmd = f'wget https://github.com/prometheus/node_exporter/releases/download/v1.2.2/node_exporter-1.2.2.linux-amd64.tar.gz;' \
        'tar xvfz node_exporter-*.*-amd64.tar.gz; '
    conn.run(install_cmd)


@task
def stop_world(conn):
    ''' Kills the committee member.'''
    conn.run('killall -9 aleph-node')

# ======================================================================================
#                                       testnet scenarios
# ======================================================================================


@task
def send_new_binary(conn):
    # 1. send new binary
    send_zip(conn, 'aleph-node-new.zip', 'bin/aleph-node-new')

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
#                                       type-script flooder
# ======================================================================================


@task
def setup_flooder(conn):
    conn.put('nvm.sh', '/home/ubuntu/')
    conn.run('bash nvm.sh')


@task
def prepare_accounts(conn):
    with open('accounts/sudo_sk', 'r') as f:
        sudo_sk = f.readline().strip()
    with open('addresses', 'r') as f:
        addr = f.readlines()[0].strip()

    nvm = 'export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && '
    '''
    --max-old-space-size=4096 - heap size
    --scale=3000 - number of accounts
    --loops-count=0 - no additional txs
    --only_flooding=true - no stats gathering
    '''
    prepare = 'node --max-old-space-size=4096 sub-flood/dist/index.js '\
        '--finalization_timeout=20000 '\
        '--scale=10000 '\
        '--total_transactions=0 '\
        '--only_flooding=true '\
        '--loops_count=0 '\
        f'--url="ws://{addr}:9944" '\
        f'--root_account_uri="{sudo_sk}" '\
        '1>prepare_accounts.log 2>&1'
    conn.run(nvm+prepare)


@task
def run_flooder(conn, pid):
    with open('addresses', 'r') as f:
        addr = f.readlines()[int(pid)].strip()
    with open('accounts/sudo_sk', 'r') as f:
        sudo_sk = f.readline().strip()

    nvm = 'export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && '
    pid = int(pid)

    '''
    --starting_account - id of account from which to start
    --scale=500 - number of tx to send. scale * n_flooders has to be <= scale from above
    '''
    run_cmd = 'node --max-old-space-size=4096 sub-flood/dist/index.js '\
        f'--starting_account={pid*1000} '\
        '--finalization_timeout=20000 '\
        '--scale=2000 '\
        '--total_transactions=20000 '\
        '--only_flooding=true '\
        '--accelerate=100 '\
        '--loops_count=4000000  '\
        '--initial_speed=1 '\
        f'--url="ws://{addr}:9944" '\
        f'--root_account_uri="{sudo_sk}" '\
        '2>flooder.log'
    conn.run(nvm+run_cmd)


@task
def monitor_flood(conn):
    with open('addresses', 'r') as f:
        addr = f.readlines()[-1].strip()
    with open('accounts/sudo_sk', 'r') as f:
        sudo_sk = f.readline().strip()

    cmd = 'node --max-old-space-size=4096 dist/index.js '\
        '--finalization_timeout=20000 '\
        '--scale=1 '\
        '--total_transactions=1 '\
        '--total_threads=1 '\
        '--keep_collecting_stats=true '\
        '--only_flooding=true '\
        '--loops_count=0 '\
        f'--url="ws://{addr}:9944" '\
        f'--root_account_uri={sudo_sk} '\
        '1>./flood.log 2>&1'

    conn.run(cmd)


# ======================================================================================
#                                       flooder
# ======================================================================================


@task
def send_flooder_binary(conn):
    # 1. send new binary
    send_zip(conn, 'flooder.zip', 'bin/flooder')


@task
def send_flooder_script(conn):
    # 1. Send script
    conn.put('bin/flooder_script.sh', '.')
    
    # 2. add exec permissions
    conn.run('chmod +x ./flooder_script.sh')


@task 
def start_flooding(conn, pid):
    conn.run(f'./flooder_script.sh {pid} > flood.log 2> flood.error')


@task
def _start_flooding(conn):
    # 1. Send script
    conn.put('bin/flooder_script.sh', '.')
    
    # 2. add exec permissions
    conn.run('chmod +x ./flooder_script.sh')

    # 3. flood
    conn.run('./flooder_script.sh > flood.log 2> flood.error')


# ======================================================================================
#                                        misc
# ======================================================================================


@task
def send_chainspec(conn):
    conn.put('chainspec.json', '.')


@task
def test(conn):
    ''' Tests if connection is ready '''

    conn.open()


@task
def schedule_termination(conn):
    with open('bin/terminate', 'r') as f:
        timeout = f.read()
        conn.run('sudo apt install -y at', hide='both')

        conn.run(f'echo "sudo shutdown -h now" | at now + {timeout} minutes')


# ======================================================================================
#                                        utils
# ======================================================================================


def send_zip(conn, file, zip_file):
    cmd = f'zip -j {zip_file} {file}'
    call(cmd.split())
    conn.put(f'{zip_file}', '.')
    conn.run(f'unzip -o /home/ubuntu/{zip_file} && rm {zip_file}')
