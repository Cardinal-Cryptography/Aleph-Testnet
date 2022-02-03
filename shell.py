'''This is a shell for orchestrating experiments on AWS EC 2'''
import os
import shutil

from functools import partial
from subprocess import run, call
from time import sleep, time
from joblib import Parallel, delayed

import boto3

from utils import *

import warnings
import yaml
warnings.filterwarnings(action='ignore', module='.*paramiko.*')

N_JOBS = 12

# ======================================================================================
#                              routines for ips
# ======================================================================================


def run_task_for_ip(task='test', ip_list=[], parallel=True, pids=None):
    '''
    Runs a task from fabfile.py on all instances in a given region.
    :param string task: name of a task defined in fabfile.py
    :param list ip_list: list of ips of hosts
    :param bool parallel: indicates whether task should be dispatched in parallel
    '''

    print(f'running task {task} in {ip_list}')

    if parallel:
        hosts = " ".join(["ubuntu@"+ip for ip in ip_list])
        pcmd = f'parallel {fab_cmd()} -H'
        if pids is None:
            cmd = pcmd + ' {} ' + task + ' ::: ' + hosts
        else:
            cmd = pcmd + ' {1} ' + task + ' --pid={2} ::: ' + \
                hosts + ' :::+ ' + ' '.join(pids)
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        cmd = f'{fab_cmd()} -H {hosts} {task}'

    try:
        return run(cmd.split(), capture_output=True)
    except Exception as _:
        print('paramiko troubles')

# ======================================================================================
#                              routines for some region
# ======================================================================================


def create_instances(region_name, image_id, n_parties, instance_type, key_name,
                     security_group_id, volume_size, tag):
    ''' Creates instances. '''

    ec2 = boto3.resource('ec2', region_name)
    instances = ec2.create_instances(ImageId=image_id,
                                     MinCount=n_parties,
                                     MaxCount=n_parties,
                                     InstanceType=instance_type,
                                     BlockDeviceMappings=[{
                                         'DeviceName': '/dev/sda1',
                                         'Ebs': {
                                             'DeleteOnTermination': True,
                                             'VolumeSize': volume_size,
                                             'VolumeType': 'gp2'
                                         },
                                     }, ],
                                     KeyName=key_name,
                                     Monitoring={'Enabled': False},
                                     InstanceInitiatedShutdownBehavior='terminate',
                                     TagSpecifications=[
                                         {
                                             'ResourceType': 'instance',
                                             'Tags': [{'Key': 'net',
                                                       'Value': tag}]
                                         }
                                     ],
                                     SecurityGroupIds=[security_group_id])

    return instances


def launch_new_instances_in_region(n_parties=1, region_name=default_region(),
                                   instance_type='t2.micro', volume_size=8, tag='dev'):
    '''Launches n_parties in a given region.'''

    print('launching instances in', region_name)

    init_key_pair(region_name)
    security_group_id = security_group_id_by_region(region_name, tag)
    image_id = image_id_in_region(region_name, 'ubuntu')

    return create_instances(region_name, image_id, n_parties, instance_type, 'aleph',
                            security_group_id, volume_size, tag)


def all_instances_in_region(region_name=default_region(), states=['running', 'pending'],
                            tag='dev'):
    '''Returns all running or pending instances in a given region.'''

    ec2 = boto3.resource('ec2', region_name)
    instances = []
    for instance in ec2.instances.all():
        if instance.state['Name'] in states:
            it = instance.tags
            if (it is None and tag == '') or (it is not None and it[0]['Key'] == 'net' and it[0]['Value'] == tag):
                instances.append(instance)

    return instances


def terminate_instances_in_region(region_name=default_region(), tag='dev'):
    '''Terminates all running instances in a given regions.'''

    ans = input(
        f"Do you want to terminate all instances in region {region_name} tagged {tag} [y]/n?")
    if ans not in ['', 'y']:
        return

    print(region_name, 'terminating instances')
    for instance in all_instances_in_region(region_name, tag=tag):
        instance.terminate()


def instances_ip_in_region(region_name=default_region(), tag='dev'):
    '''Returns ips of all running or pending instances in a given region.'''

    ips = []

    for instance in all_instances_in_region(region_name, tag=tag):
        ips.append(instance.public_ip_address)

    return ips


def instances_state_in_region(region_name=default_region(), tag='dev'):
    '''Returns states of all instances in a given regions.'''

    states = []
    possible_states = ['running', 'pending', 'shutting-down', 'terminated']
    for instance in all_instances_in_region(region_name, possible_states, tag=tag):
        states.append(instance.state['Name'])

    return states


def run_task_in_region(task='test', region_name=default_region(), parallel=True, tag='dev', pids=None):
    '''
    Runs a task from fabfile.py on all instances in a given region.
    :param string task: name of a task defined in fabfile.py
    :param string region_name: region from which instances are picked
    :param bool parallel: indicates whether task should be dispatched in parallel
    '''

    print(f'running task {task} in {region_name}')

    ip_list = instances_ip_in_region(region_name, tag)
    if parallel:
        hosts = " ".join(["ubuntu@"+ip for ip in ip_list])
        pcmd = f'parallel {fab_cmd()} -H'
        if pids is None:
            cmd = pcmd + ' {} ' + task + ' ::: ' + hosts
        else:
            pids = [str(pid) for pid in pids]
            cmd = pcmd + ' {1} ' + task + ' --pid={2} ::: ' + \
                hosts + ' :::+ ' + ' '.join(pids)
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        cmd = f'{fab_cmd()} -H {hosts} {task}'

    try:
        return run(cmd.split(), capture_output=True)
    except Exception as _:
        print('paramiko troubles')


def run_cmd_in_region(shcmd='ls', region_name=default_region(), tag='dev'):
    '''
    Runs a shell command cmd on all instances in a given region.
    :param string cmd: a shell command that is run on instances
    :param string region_name: region from which instances are picked
    :param bool output: indicates whether output of cmd is needed
    '''

    print(f'running command {shcmd} in {region_name}')

    ip_list = instances_ip_in_region(region_name, tag)
    results = []
    for ip in ip_list:
        cmd = f'ssh -o "StrictHostKeyChecking no" -q -i key_pairs/aleph.pem ubuntu@{ip} -t "{shcmd}"'
        results.append(call(cmd, shell=True))

    return results


def allow_traffic_in_region(region_name=default_region(), ip_list=[], tag='dev'):
    '''Updates security group with addresses in given ip_list.'''

    update_security_group(region_name, ip_list, tag)


def wait_in_region(target_state, region_name=default_region(), tag='dev'):
    '''Waits until all machines in a given region reach a given state.'''

    print('waiting in', region_name)

    instances = all_instances_in_region(region_name, tag=tag)
    if target_state == 'running':
        for i in instances:
            i.wait_until_running()
    elif target_state == 'terminated':
        for i in instances:
            i.wait_until_terminated()
    elif target_state == 'open 22':
        for i in instances:
            cmd = f'{fab_cmd()} -H ubuntu@{i.public_ip_address} test'
            while run(cmd.split(), capture_output=True).returncode != 0:
                sleep(.1)
                print('.', end='')
        print()
        sleep(10)
    if target_state == 'ssh ready':
        ids = [instance.id for instance in instances]
        initializing = True
        while initializing:
            responses = boto3.client(
                'ec2', region_name).describe_instance_status(InstanceIds=ids)
            statuses = responses['InstanceStatuses']
            all_initialized = True
            if statuses:
                for status in statuses:
                    if status['InstanceStatus']['Status'] != 'ok' or status['SystemStatus']['Status'] != 'ok':
                        all_initialized = False
            else:
                all_initialized = False

            if all_initialized:
                initializing = False
            else:
                print('.', end='')
                sleep(5)
        print()


def wait_install_in_region(type, region_name=default_region(), tag='dev'):
    '''Checks if installation has finished on all instances in a given region.'''

    results = []
    cmd = f"tail -1 {type}_setup.log"
    run(cmd.split(), capture_output=True)
    results = run_cmd_in_region(cmd, region_name, tag)
    for result in results:
        if len(result) < 4 or result[:4] != b'done':
            return False

    print(f'installation in {region_name} finished')
    return True

# ======================================================================================
#                              routines for all regions
# ======================================================================================


def exec_for_regions(func, regions=use_regions(), parallel=True, pids=None):
    '''A helper function for running routines in all regions.'''

    results = []
    if parallel:
        try:
            if pids is None:
                results = Parallel(n_jobs=N_JOBS)(
                    delayed(func)(region_name) for region_name in regions)
            else:
                results = Parallel(n_jobs=N_JOBS)(delayed(func)(
                    region_name, pids=pids[region_name]) for region_name in regions)

        except Exception as e:
            print('error during collecting results', type(e), e)
    else:
        for region_name in regions:
            results.append(func(region_name))

    if results and isinstance(results[0], list):
        return [res for res_list in results for res in res_list]

    return results


def launch_new_instances(nppr, instance_type='t2.micro', volume_size=8, tag='dev'):
    '''
    Launches n_parties_per_region in ever region from given regions.
    :param dict nppr: dict region_name --> n_parties_per_region
    '''

    regions = nppr.keys()

    failed = []
    print('launching instances')
    for region_name in regions:
        print(region_name, '', end='')
        instances = launch_new_instances_in_region(
            nppr[region_name], region_name, instance_type, volume_size, tag)
        if not instances:
            failed.append(region_name)

    tries = 5
    while failed and tries:
        tries -= 1
        sleep(5)
        print('there were problems in launching instances in regions',
              *failed, 'retrying')
        for region_name in failed.copy():
            print(region_name, '', end='')
            instances = launch_new_instances_in_region(
                nppr[region_name], region_name, instance_type, volume_size, tag)
            if instances:
                failed.remove(region_name)

    if failed:
        print('reporting complete failure in regions', failed)


def terminate_instances(regions=use_regions(), parallel=True, tag='dev'):
    '''Terminates all instances in ever region from given regions.'''

    return exec_for_regions(partial(terminate_instances_in_region, tag=tag), regions, parallel)


def all_instances(regions=use_regions(), states=['running', 'pending'], parallel=True, tag='dev'):
    '''Returns all running or pending instances from given regions.'''

    return exec_for_regions(partial(all_instances_in_region, states=states, tag=tag), regions, parallel)


def instances_ip(regions=use_regions(), parallel=True, tag='dev'):
    '''Returns ip addresses of all running or pending instances from given regions.'''

    return exec_for_regions(partial(instances_ip_in_region, tag=tag), regions, parallel)


def instances_state(regions=use_regions(), parallel=True, tag='dev'):
    '''Returns states of all instances in given regions.'''

    return exec_for_regions(partial(instances_state_in_region, tag=tag), regions, parallel)


def run_task(task='test', regions=use_regions(), parallel=True, tag='dev', pids=None):
    '''
    Runs a task from fabfile.py on all instances in all given regions.
    :param string task: name of a task defined in fabfile.py
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    '''

    exec_for_regions(partial(run_task_in_region, task,
                     parallel=parallel, tag=tag), regions, parallel, pids)


def run_cmd(cmd='ls', regions=use_regions(), parallel=True, tag='dev'):
    '''
    Runs a shell command cmd on all instances in all given regions.
    :param string cmd: a shell command that is run on instances
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_cmd_in_region, cmd, tag=tag), regions, parallel)


def allow_traffic(regions=use_regions(), ip_list=[], parallel=True, tag='dev'):
    '''
    Adds ip_list to security group enabling traffic among instances.
    :param list ip_list: list of all allowed ips
    :param list regions: collections of regions in which the tast should be performed
    '''

    exec_for_regions(partial(allow_traffic_in_region,
                     ip_list=ip_list, tag=tag), regions, parallel)


def allow_all_traffic(regions=use_regions(), tag='dev'):
    exec_for_regions(partial(allow_all_traffic_in_region,
                     tag=tag), regions, False)


def wait(target_state, regions=use_regions(), tag='dev'):
    '''Waits until all machines in all given regions reach a given state.'''

    exec_for_regions(partial(wait_in_region, target_state, tag=tag), regions)


def wait_install(type, regions=use_regions(), tag='dev'):
    '''Waits till installation finishes in all given regions.'''

    while True:
        all_completed = True

        for r in regions:
            if wait_install_in_region(type, r, tag):
                all_completed = False
                sleep(.5)
        if all_completed:
            return

# ======================================================================================
#                                        shortcuts
# ======================================================================================


tr = run_task_in_region
t = run_task

cmr = run_cmd_in_region
cm = run_cmd

tir = terminate_instances_in_region
ti = terminate_instances

# ======================================================================================
#                                      dispatch
# ======================================================================================


def upgrade_binary(regions, tag='dev', delay=0):
    for ip in instances_ip(regions, 1, tag):
        run_task_for_ip('upgrade-binary', [ip], 0)
        if delay > 0:
            sleep(delay)
        else:
            input("to proceed, press any key")


def prepare_accounts(region, tag):
    ip = instances_ip_in_region(region, tag)[0]
    run_task_for_ip('prepare-accounts', [ip], False)


def setup_flooder(n_flooders, regions, instance_type, tag):
    flood_tag = tag+"-flood"

    nhpr = n_parties_per_regions(n_flooders, regions)
    launch_new_instances(nhpr, instance_type, 8, flood_tag)

    color_print('waiting till ports are open on machines')
    wait('open 22', regions, flood_tag)

    run_task('setup-flooder', regions, True, flood_tag)

    ip_list = instances_ip(regions, True, tag)
    ip_list += instances_ip(regions, True, flood_tag)

    # add flood machines to nodes firewall
    allow_traffic(regions, ip_list, True, tag)


def setup_infrastructure(n_parties, chain='dev', regions=use_regions(), instance_type='t2.micro',
                         volume_size=8, tag='dev', benchmark_config=None, terminate_in_min=None, n_validators=None, **chain_flags):
    n_validators = n_validators or n_parties
    start = time()
    parallel = n_parties > 1

    color_print('launching machines')
    nhpr = n_parties_per_regions(n_parties, regions)
    launch_new_instances(nhpr, instance_type, volume_size, tag)

    color_print('waiting for transition from pending to running')
    wait('running', regions, tag)

    color_print('generating keys & addresses files')
    pids, ip2pid, ip_list, c = {}, {}, [], 0
    for r in regions:
        ipl = instances_ip_in_region(r, tag)
        pids[r] = [str(pid) for pid in range(c, c + len(ipl))]
        ip2pid.update({ip: pid for (ip, pid) in zip(ipl, pids[r])})
        c += len(ipl)
        ip_list.extend(ipl)

    allow_traffic(regions, ip_list, parallel, tag)

    write_addresses(ip_list)

    os.makedirs('data', exist_ok=True)

    parties = generate_accounts(
        n_parties, chain, 'validator_phrases', 'validator_accounts')
    bootstrap_chain(parties[:n_validators], chain,
                    benchmark_config=benchmark_config, **chain_flags)
    generate_p2p_keys(parties)

    color_print('waiting till ports are open on machines')
    wait('open 22', regions, tag)

    color_print('setup')
    color_print(run_task('setup', regions, parallel, tag).stderr)

    color_print('send data')
    color_print(run_task('send-data', regions, parallel, tag, pids).stderr)

    color_print('start nginx')
    color_print(run_task('run-nginx', regions, parallel, tag).stderr)

    color_print(
        f'establishing the environment took {round(time() - start, 2)}s')

    if terminate_in_min is not None:
        color_print('schedule termination')
        with open('bin/terminate', 'w') as f:
            f.write(f'{terminate_in_min}')
        color_print(run_task('schedule-termination', regions, parallel, tag).stderr)

    return pids


def send_flooder_to_nodes(flooder_binary, regions=use_regions(), tag='dev'):
    os.makedirs('bin', exist_ok=True)
    shutil.copy(flooder_binary, 'bin/flooder')

    color_print('send-flooder')
    run_task('send-flooder-binary', regions, True, tag)


def setup_nodes(n_parties, chain='dev', regions=use_regions(), instance_type='t2.micro', volume_size=8, tag='dev',
                node_flags=None, benchmark_config=None, chain_flags=None, terminate_in_min=None, n_validators=None):
    '''Setups the infrastructure and the binary. After it is successful, the 'dispatch'
    task has to be run to start the nodes.'''

    pids = setup_infrastructure(
        n_parties, chain, regions, instance_type, volume_size, tag, benchmark_config, terminate_in_min, n_validators, **(chain_flags or dict()))

    parallel = n_parties > 1

    color_print('send the binary')
    run_task('send-binary', regions, parallel, tag)

    save_node_flags(node_flags or dict())
    run_task('create-dispatch-cmd', regions, parallel, tag, pids)

    run_task('install-prometheus-exporter', regions, parallel, tag)

    return pids


def prepare_benchmark_script(benchmark_config, n_parties, regions=use_regions(), tag='dev'):
    n_of_accounts = int(benchmark_config.get('n_of_accounts', 1000))
    flooder_binary = benchmark_config.get('flooder_binary', 'flooder')
    transactions = int(benchmark_config.get('transactions', 1000))
    rate_limiting = benchmark_config.get('rate_limiting', None)

    script = '#!/usr/bin/env bash\n' \
        'pid="$1"\n' \
        f'first_account=$((pid*{(n_of_accounts // n_parties)}))\n' \
        f'RUST_LOG=info ./flooder --nodes localhost:9944' \
        f' --transactions={transactions}' \
        ' --skip-initialization'\
        ' --first-account-in-range="$first_account"'

    if rate_limiting is not None:
        transactions_in_interval, interval_secs = rate_limiting
        script += f' --transactions-in-interval={transactions_in_interval} --interval-secs={interval_secs}'

    script += '\n'

    with open('bin/flooder_script.sh', 'w') as f:
        f.write(script)

    color_print('send-flooder-script')
    run_task('send-flooder-script', regions, True, tag)

    send_flooder_to_nodes(flooder_binary, regions, tag)


def setup_benchmark(n_parties, chain='dev', regions=use_regions(), instance_type='t2.micro', volume_size=8, tag='dev',
                    node_flags=None, benchmark_config=None, chain_flags=None, terminate_in_min=60):
    '''Setups the infrastructure and the binary. After it is successful, the 'dispatch'
    task has to be run to start the benchmark.'''

    pids = setup_nodes(n_parties, chain, regions, instance_type,
                       volume_size, tag, node_flags, benchmark_config, chain_flags, terminate_in_min)

    allow_all_traffic(regions, tag)

    if benchmark_config is not None:
        prepare_benchmark_script(benchmark_config, n_parties, regions, tag)

    return pids


def setup_flooding(region=default_region(), tag='flooders'):
    color_print('launching instance')
    launch_new_instances_in_region(n_parties=1, region_name=region, tag=tag)

    print('Flooder ip:', instances_ip_in_region(region_name=region, tag=tag))

    color_print('waiting till ports are open on machines')
    wait('open 22', [region], tag)

    color_print('sending flooder binary')
    run_task('setup', regions=[region], parallel=False, tag=tag)
    run_task('send-flooder-binary', regions=[region], parallel=False, tag=tag)

    color_print('start flooding')
    run_task('start-flooding', regions=[region], parallel=False, tag=tag)


def run_devnet(n_parties, regions=use_regions(), instance_type='t2.micro'):
    pids = setup_infrastructure(n_parties, regions, instance_type)

    parallel = n_parties > 1

    color_print('install docker and dependencies')
    run_task('docker-setup', regions, parallel)

    color_print('wait till installation finishes')
    wait_install('docker', regions)

    color_print('run docker compose')
    run_task('run-docker-compose', regions, parallel, False, pids)

    instances_state(testnet_regions(), 'testnet')


def setup_prometheus(region=default_region(), tag='prometheus', target_regions=use_regions(), target_tag="dev"):
    color_print('retrieving target ips')
    ips = [ip for region in target_regions for ip in instances_ip_in_region(region_name=region, tag=target_tag)]
    print('target ips:', ips)

    color_print('launching instance')
    launch_new_instances_in_region(n_parties=1, region_name=region, tag=tag)

    color_print('waiting till ports are open on machines')
    wait('open 22', [region], tag)

    print('prometheus ip:', instances_ip_in_region(region_name=region, tag=tag))

    color_print('setup')
    run_task('setup', regions=[region], parallel=False, tag=tag)

    color_print('creating prometheus.yml configuration file')
    config = create_prometheus_configuration(ips)
    with open('prometheus.yml', 'w') as yml_file:
        yaml.dump(config, yml_file)

    color_print('sending prometheus.yml configuration file')
    run_task('send-prometheus-config', regions=[region], parallel=False, tag=tag)

    color_print('intalling prometheus')
    run_task('install-prometheus', regions=[region], parallel=False, tag=tag)
