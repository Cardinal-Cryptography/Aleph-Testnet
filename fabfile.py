'''Routines called by fab. Assumes that all are called from */experiments/aws.'''

from fabric import task
from numpy import add


# ======================================================================================
#                                    installation
# ======================================================================================

@task
def setup(conn):
    ''' Install dependencies in a nonblocking way.'''

    conn.put('setup.sh', '.')
    conn.sudo('apt update', hide='both')
    conn.sudo('apt install dtach', hide='both')
    conn.run(
        'PATH="$PATH:/snap/bin" && dtach -n `mktemp -u /tmp/dtach.XXXX` bash setup.sh', hide='both')


@task
def setup_completed(conn):
    ''' Check if installation completed.'''

    result = conn.run('tail -1 setup.log')
    return result.stdout.strip()


@task
def clone_repo(conn):
    '''Clones main repo.'''

    path = '/home/ubuntu/go/src/gitlab.com/alephledger/consensus-go'
    # delete current repo
    conn.run(f'rm -rf {path}')
    # clone using deployment token
    user_token = 'gitlab+deploy-token-70309:G2jUsynd3TQqsvVfn4T7'
    conn.run(
        f'git clone http://{user_token}@gitlab.com/alephledger/consensus-go.git {path}')


@task
def build_gomel(conn):
    conn.run(f'PATH="$PATH:/snap/bin" && go build /home/ubuntu/go/src/gitlab.com/alephledger/consensus-go/cmd/gomel')


@task
def inst_deps(conn):
    conn.put('deps.sh', '.')
    conn.run(
        'PATH="$PATH:/snap/bin" && dtach -n `mktemp -u /tmp/dtach.XXXX` bash deps.sh', hide='both')

# ======================================================================================
#                                   syncing local version
# ======================================================================================


@task
def mkdir(conn):
    conn.run('mkdir -p /home/ubuntu/testnet1/bin')
    conn.run('sudo apt install unzip -y')


@task
def send_addrs(conn):
    ''' Sends addresses and fixes ip address. '''
    path = '/home/ubuntu/testnet1'
    conn.put('data/addresses', path+'/addrs')
    with conn.cd(path):
        conn.run(
            f'sed s/{conn.host}/$(hostname --ip-address)/g < addrs > addresses')


@task
def send_data(conn, pid):
    ''' Sends keys and addresses. '''
    # sends all the keys, refactor to send only the needed one

    conn.put('data.zip', '/home/ubuntu/testnet1/')
    conn.run('unzip /home/ubuntu/testnet1/data.zip')
    conn.run('mv /home/ubuntu/data/* /tmp')
    # send_addrs(conn)


@task
def send_binary(conn):
    path = '/home/ubuntu/testnet1/bin/'
    conn.put('bin/aleph-node', path)

# ======================================================================================
#                                   run experiments
# ======================================================================================


@task
def run_protocol(conn, pid, delay='0'):
    ''' Runs the protocol.'''

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

    reserved_nodes = " ".join(reserved_nodes)

    with conn.cd(path):
        # conn.run(
        # f'./bin/aleph-node purge-chain --base-path /tmp/{auth} --chain testnet1 -y')
        cmd = f'./bin/aleph-node \
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
                --node-key-file /tmp/{auth}/libp2p_secret'
        print(cmd)
    # conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` {cmd}')


@task
def run_protocol_profiler(conn, pid, delay='0'):
    ''' Runs the protocol.'''

    path = '/home/ubuntu/go/src/gitlab.com/alephledger/consensus-go'
    with conn.cd(path):
        conn.run(f'PATH="$PATH:/snap/bin" && go build {path}/cmd/gomel')
        cmd = f'./gomel --priv {pid}.pk\
                    --keys_addrs committee.ka\
                    --delay {int(float(delay))}\
                    --setup {"true" if delay=="0" else "false"}'
        if int(pid) % 16 == 0:
            cmd += ' --cpuprof cpuprof --memprof memprof --mf 5 --bf 0'
        conn.run(f'dtach -n `mktemp -u /tmp/dtach.XXXX` {cmd}')


@task
def stop_world(conn):
    ''' Kills the committee member.'''

    conn.run('pkill --signal ABRT -f gomel')

# ======================================================================================
#                                        get data
# ======================================================================================


@task
def get_profile(conn, pid):
    ''' Retrieves cpuprof and memprof from the server.'''

    path = '/home/ubuntu/go/src/gitlab.com/alephledger/consensus-go'
    with conn.cd(path):
        conn.run(f'cp cpuprof {pid}.cpuprof')
        conn.run(f'cp memprof {pid}.memprof')
        conn.run(f'zip -q prof.zip {pid}.cpuprof {pid}.memprof')
    conn.get(f'{path}/prof.zip', f'../results/{pid}.prof.zip')


@task
def get_dag(conn, pid):
    ''' Retrieves aleph.dag from the server.'''

    path = '/home/ubuntu/go/src/gitlab.com/alephledger/consensus-go'
    with conn.cd(path):
        conn.run(f'zip -q {pid}.dag.zip {pid}.dag')
    conn.get(f'{path}/{pid}.dag.zip', f'../results/{pid}.dag.zip')


@task
def get_log(conn, pid):
    ''' Retrieves aleph.log from the server.'''

    path = '/home/ubuntu/go/src/gitlab.com/alephledger/consensus-go'
    with conn.cd(path):
        conn.run(f'zip -q {pid}.logs.zip {pid}.json {pid}.setup.json')
    conn.get(f'{path}/{pid}.logs.zip', f'../results/{pid}.log.zip')

# ======================================================================================
#                                        misc
# ======================================================================================


@task
def test(conn):
    ''' Tests if connection is ready '''

    conn.open()
