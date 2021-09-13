'''This is a shell for orchestrating experiments on AWS EC 2'''
import json
import os
import shutil

from functools import partial
from glob import glob
from subprocess import call, check_output, DEVNULL
from time import sleep, time
from joblib import Parallel, delayed

import boto3
import numpy as np
import zipfile

from utils import *

import warnings
warnings.filterwarnings(action='ignore', module='.*paramiko.*')

N_JOBS = 12

# ======================================================================================
#                              routines for ips
# ======================================================================================


def run_task_for_ip(task='test', ip_list=[], parallel=False, output=False, pids=None):
    '''
    Runs a task from fabfile.py on all instances in a given region.
    :param string task: name of a task defined in fabfile.py
    :param list ip_list: list of ips of hosts
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    print(f'running task {task} in {ip_list}')

    if parallel:
        hosts = " ".join(["ubuntu@"+ip for ip in ip_list])
        pcmd = 'parallel fab -i key_pairs/aleph.pem -H'
        if pids is None:
            cmd = pcmd + ' {} ' + task + ' ::: ' + hosts
        else:
            cmd = pcmd + ' {1} ' + task + ' --pid={2} ::: ' + \
                hosts + ' :::+ ' + ' '.join(pids)
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        cmd = f'fab -i key_pairs/aleph.pem -H {hosts} {task}'

    try:
        if output:
            return check_output(cmd.split())
        return call(cmd.split(), stdout=DEVNULL)
    except Exception as _:
        print('paramiko troubles')

# ======================================================================================
#                              routines for some region
# ======================================================================================


def latency_in_region(region_name):
    if region_name == default_region():
        region_name = default_region()

    print('finding latency', region_name)

    ip_list = instances_ip_in_region(region_name)
    assert ip_list, 'there are no instances running!'

    reps = 10
    cmd = f'parallel nping -q -c {reps} -p 22 ::: ' + ' '.join(ip_list)
    output = check_output(cmd.split()).decode()
    lines = output.split('\n')
    times = []
    for i in range(len(lines)//5):  # equivalent to range(len(ip_list))
        times_ = lines[5*i+2].split('|')
        times_ = [t.split()[2][:-2] for t in times_]
        times.append([float(t.strip()) for t in times_])

    latency = [f'{round(t, 2)}ms' for t in np.mean(times, 0)]
    latency = dict(zip(['max', 'min', 'avg'], latency))

    return latency


def create_instances(region_name, image_id, n_parties, instance_type, key_name,
                     security_group_id, volume_size):
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
                                     IamInstanceProfile={
                                         'Arn': 'arn:aws:iam::436875894086:instance-profile/EC2DockerCloudwatchLogs'
                                     },
                                     SecurityGroupIds=[security_group_id])

    return instances


def launch_new_instances_in_region(n_parties=1, region_name=default_region(),
                                   instance_type='t2.micro', volume_size=8):
    '''Launches n_parties in a given region.'''

    print('launching instances in', region_name)

    init_key_pair(region_name)
    security_group_id = security_group_id_by_region(region_name)
    image_id = image_id_in_region(region_name, 'ubuntu')

    return create_instances(region_name, image_id, n_parties, instance_type, 'aleph',
                            security_group_id, volume_size)


def all_instances_in_region(region_name=default_region(), states=['running', 'pending']):
    '''Returns all running or pending instances in a given region.'''

    ec2 = boto3.resource('ec2', region_name)
    instances = []
    for instance in ec2.instances.all():
        if instance.state['Name'] in states and instance.instance_type != "c5.4xlarge":
            instances.append(instance)

    return instances


def terminate_instances_in_region(region_name=default_region()):
    '''Terminates all running instances in a given regions.'''

    ans = input(
        f"Do you want to terminate all instances in region {region_name} [y]/n?")
    if ans not in ['', 'y']:
        return

    print(region_name, 'terminating instances')
    for instance in all_instances_in_region(region_name):
        instance.terminate()


def instances_ip_in_region(region_name=default_region()):
    '''Returns ips of all running or pending instances in a given region.'''

    ips = []

    for instance in all_instances_in_region(region_name):
        ips.append(instance.public_ip_address)

    return ips


def instances_state_in_region(region_name=default_region()):
    '''Returns states of all instances in a given regions.'''

    states = []
    possible_states = ['running', 'pending', 'shutting-down', 'terminated']
    for instance in all_instances_in_region(region_name, possible_states):
        states.append(instance.state['Name'])

    return states


def run_task_in_region(task='test', region_name=default_region(), parallel=True, output=False, pids=None):
    '''
    Runs a task from fabfile.py on all instances in a given region.
    :param string task: name of a task defined in fabfile.py
    :param string region_name: region from which instances are picked
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    print(f'running task {task} in {region_name}')

    ip_list = instances_ip_in_region(region_name)
    if parallel:
        hosts = " ".join(["ubuntu@"+ip for ip in ip_list])
        pcmd = 'parallel fab -i key_pairs/aleph.pem -H'
        if pids is None:
            cmd = pcmd + ' {} ' + task + ' ::: ' + hosts
        else:
            cmd = pcmd + ' {1} ' + task + ' --pid={2} ::: ' + \
                hosts + ' :::+ ' + ' '.join(pids)
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        cmd = f'fab -i key_pairs/aleph.pem -H {hosts} {task}'

    try:
        if output:
            return check_output(cmd.split())
        return call(cmd.split(), stdout=DEVNULL)
    except Exception as _:
        print('paramiko troubles')


def run_cmd_in_region(cmd='tail -f ~/go/src/gitlab.com/alephledger/consensus-go/aleph.log', region_name=default_region(), output=False):
    '''
    Runs a shell command cmd on all instances in a given region.
    :param string cmd: a shell command that is run on instances
    :param string region_name: region from which instances are picked
    :param bool output: indicates whether output of cmd is needed
    '''

    print(f'running command {cmd} in {region_name}')

    ip_list = instances_ip_in_region(region_name)
    results = []
    for ip in ip_list:
        cmd_ = f'ssh -o "StrictHostKeyChecking no" -q -i key_pairs/aleph.pem ubuntu@{ip} -t "{cmd}"'
        if output:
            results.append(check_output(cmd_, shell=True))
        else:
            results.append(call(cmd_, shell=True))

    return results


def allow_traffic_in_region(ip_list, region_name=default_region()):
    '''Updates security group with addresses in given ip_list.'''

    return update_security_group(region_name, ip_list=ip_list)


def wait_in_region(target_state, region_name=default_region()):
    '''Waits until all machines in a given region reach a given state.'''

    if region_name == default_region():
        region_name = default_region()

    print('waiting in', region_name)

    instances = all_instances_in_region(region_name)
    if target_state == 'running':
        for i in instances:
            i.wait_until_running()
    elif target_state == 'terminated':
        for i in instances:
            i.wait_until_terminated()
    elif target_state == 'open 22':
        for i in instances:
            cmd = f'fab -i key_pairs/aleph.pem -H ubuntu@{i.public_ip_address} test'
            while call(cmd.split(), stdout=DEVNULL, stderr=DEVNULL):
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
                import sys
                sys.stdout.flush()
                sleep(5)
        print()


def wait_install_in_region(type, region_name=default_region()):
    '''Checks if installation has finished on all instances in a given region.'''

    results = []
    cmd = f"tail -1 {type}_setup.log"
    results = run_cmd_in_region(cmd, region_name, output=True)
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


def launch_new_instances(nppr, instance_type='t2.micro', volume_size=8):
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
            nppr[region_name], region_name, instance_type, volume_size)
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
                nppr[region_name], region_name, instance_type)
            if instances:
                failed.remove(region_name)

    if failed:
        print('reporting complete failure in regions', failed)


def terminate_instances(regions=use_regions(), parallel=True):
    '''Terminates all instances in ever region from given regions.'''

    return exec_for_regions(terminate_instances_in_region, regions, parallel)


def all_instances(regions=use_regions(), states=['running', 'pending'], parallel=True):
    '''Returns all running or pending instances from given regions.'''

    return exec_for_regions(partial(all_instances_in_region, states=states), regions, parallel)


def instances_ip(regions=use_regions(), parallel=True):
    '''Returns ip addresses of all running or pending instances from given regions.'''

    return exec_for_regions(instances_ip_in_region, regions, parallel)


def instances_state(regions=use_regions(), parallel=True):
    '''Returns states of all instances in given regions.'''

    return exec_for_regions(instances_state_in_region, regions, parallel)


def run_task(task='test', regions=use_regions(), parallel=True, output=False, pids=None):
    '''
    Runs a task from fabfile.py on all instances in all given regions.
    :param string task: name of a task defined in fabfile.py
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_task_in_region, task, parallel=parallel, output=output), regions, parallel, pids)


def run_cmd(cmd='ls', regions=use_regions(), parallel=True, output=False):
    '''
    Runs a shell command cmd on all instances in all given regions.
    :param string cmd: a shell command that is run on instances
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_cmd_in_region, cmd, output=output), regions, parallel)


def allow_traffic(ip_list, regions=use_regions(), parallel=True):
    '''
    Adds ip_list to security group enabling traffic among instances.
    :param list ip_list: list of all allowed ips
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(allow_traffic_in_region, ip_list), regions, parallel)


def wait(target_state, regions=use_regions()):
    '''Waits until all machines in all given regions reach a given state.'''

    exec_for_regions(partial(wait_in_region, target_state), regions)


def wait_install(type, regions=use_regions()):
    '''Waits till installation finishes in all given regions.'''

    wait_for_regions = regions.copy()
    while wait_for_regions:
        results = Parallel(n_jobs=N_JOBS)(
            delayed(wait_install_in_region)(type, r) for r in wait_for_regions)

        wait_for_regions = [r for i, r in enumerate(
            wait_for_regions) if not results[i]]
        sleep(1)

# ======================================================================================
#                                        shortcuts
# ======================================================================================


tr = run_task_in_region
t = run_task

cmr = run_cmd_in_region
cm = run_cmd

tir = terminate_instances_in_region
ti = terminate_instances


def rs(): return run_protocol(7, use_regions(), 't2.micro')

# ======================================================================================
#                                      dispatch
# ======================================================================================


def setup(n_parties, chain='dev', regions=use_regions(), instance_type='t2.micro', volume_size=8):
    start = time()
    parallel = n_parties > 1

    color_print('launching machines')
    nhpr = n_parties_per_regions(n_parties, regions)
    launch_new_instances(nhpr, instance_type, volume_size)

    color_print('waiting for transition from pending to running')
    wait('running', regions)

    color_print('generating keys & addresses files')
    pids, ip2pid, ip_list, c = {}, {}, [], 0
    for r in regions:
        ipl = instances_ip_in_region(r)
        pids[r] = [str(pid) for pid in range(c, c+len(ipl))]
        ip2pid.update({ip: pid for (ip, pid) in zip(ipl, pids[r])})
        c += len(ipl)
        ip_list.extend(ipl)

    allow_traffic(ip_list, regions)

    write_addresses(ip_list)

    if not os.path.exists('data'):
        os.mkdir('data')
    validator_accounts = generate_validator_accounts(n_parties, chain)
    bootstrap_chain(n_parties, validator_accounts)
    generate_p2p_keys(validator_accounts)

    color_print('waiting till ports are open on machines')
    wait('open 22', regions)

    color_print('setup')
    run_task('setup', regions, parallel)

    color_print('send data')
    run_task('send-data', regions, parallel, False, pids)

    color_print('start nginx')
    run_task('run-nginx', regions, parallel)

    color_print(f'establishing the environment took {round(time()-start, 2)}s')

    return pids


def run_protocol(n_parties, regions=use_regions(), instance_type='t2.micro', volume_size=8):
    '''Runs the protocol.'''

    pids = setup(n_parties, regions, instance_type, volume_size)

    parallel = n_parties > 1

    color_print('send the binary')
    run_task('send-binary', regions, parallel)

    # run the experiment
    run_task('run-protocol', regions, parallel, False, pids)


def run_devnet(n_parties, regions=use_regions(), instance_type='t2.micro'):
    pids = setup(n_parties, regions, instance_type)

    parallel = n_parties > 1

    color_print('install docker and dependencies')
    run_task('docker-setup', regions, parallel)

    color_print('wait till installation finishes')
    wait_install('docker', regions)

    color_print('run docker compose')
    run_task('run-docker-compose', regions, parallel, False, pids)
