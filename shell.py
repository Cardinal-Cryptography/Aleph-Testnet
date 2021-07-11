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

from utils import image_id_in_region, default_region, init_key_pair, security_group_id_by_region, use_regions, generate_keys, n_parties_per_regions, color_print, write_addresses

import warnings
warnings.filterwarnings(action='ignore',module='.*paramiko.*')

N_JOBS = 12

#======================================================================================
#                              routines for ips
#======================================================================================

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
        cmd = 'parallel fab -i key_pairs/aleph.pem -H {} '+task+' ::: '+hosts
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        if pids is None:
            cmd = f'fab -i key_pairs/aleph.pem -H {hosts} {task}'
        else:
            if len(ip_list) > 1:
                print('works only for one ip, aborting')
                return
            cmd = f'fab -i key_pairs/aleph.pem -H {hosts} {task} --pid={pids[0]}'

    try:
        if output:
            return check_output(cmd.split())
        return call(cmd.split())
    except Exception as _:
        print('paramiko troubles')

#======================================================================================
#                              routines for some region
#======================================================================================

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


def create_instances(region_name, image_id, n_parties, instance_type, key_name, security_group_id):
    ''' Creates instances. '''

    ec2 = boto3.resource('ec2', region_name)
    instances = ec2.create_instances(ImageId=image_id,
                                 MinCount=n_parties, MaxCount=n_parties,
                                 InstanceType=instance_type,
                                 BlockDeviceMappings=[ {
                                     'DeviceName': '/dev/xvda',
                                     'Ebs': {
                                         'DeleteOnTermination': True,
                                         'VolumeSize': 8,
                                         'VolumeType': 'gp2'
                                     },
                                 }, ],
                                 KeyName=key_name,
                                 Monitoring={ 'Enabled': False },
                                 SecurityGroupIds = [security_group_id])

    return instances


def launch_new_instances_in_region(n_parties=1, region_name=default_region(), instance_type='t2.micro'):
    '''Launches n_parties in a given region.'''

    print('launching instances in', region_name)

    init_key_pair(region_name)
    security_group_id = security_group_id_by_region(region_name)
    image_id = image_id_in_region(region_name, 'ubuntu')

    return create_instances(region_name, image_id, n_parties, instance_type, 'aleph', security_group_id)


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


def run_task_in_region(task='test', region_name=default_region(), parallel=False, output=False, pids=None, delay=0):
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
            if not delay:
                cmd = pcmd + ' {1} ' + task + ' --pid={2} ::: ' + hosts + ' :::+ ' + ' '.join(pids)
            else:
                sleep = round(delay - time(), 0)
                cmd = pcmd + ' {1} ' + task + ' --pid={2} --delay={3} ::: ' + hosts + ' :::+ ' + ' '.join(pids) + ' :::+ ' + ' '.join([str(sleep)] * len(pids))
    else:
        hosts = ",".join(["ubuntu@"+ip for ip in ip_list])
        cmd = f'fab -i key_pairs/aleph.pem -H {hosts} {task}'

    try:
        if output:
            return check_output(cmd.split())
        return call(cmd.split())
    except Exception as _:
        print('paramiko troubles')


def send_file_in_region(path='cmd/gomel/main.go', region_name=default_region()):
    local = '../../' + path
    remote = 'go/src/gitlab.com/alephledger/consensus-go/' + path

    ip_list = instances_ip_in_region(region_name)
    hosts = " ".join(["ubuntu@"+ip for ip in ip_list])
    scp = 'scp -o StrictHostKeyChecking=no -i key_pairs/aleph.pem'
    cmd = 'parallel ' + scp + ' ' + local + ' {}:' + remote + ' ::: ' + hosts
    try:
        return call(cmd.split())
    except Exception as e:
        print(e)


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


def wait_in_region(target_state, region_name=default_region()):
    '''Waits until all machines in a given region reach a given state.'''

    if region_name == default_region():
        region_name = default_region()

    print('waiting in', region_name)

    instances = all_instances_in_region(region_name)
    if target_state == 'running':
        for i in instances: i.wait_until_running()
    elif target_state == 'terminated':
        for i in instances: i.wait_until_terminated()
    elif target_state == 'open 22':
        for i in instances:
            cmd = f'fab -i key_pairs/aleph.pem -H ubuntu@{i.public_ip_address} test'
            while call(cmd.split(), stderr=DEVNULL):
                sleep(.1)
    if target_state == 'ssh ready':
        ids = [instance.id for instance in instances]
        initializing = True
        while initializing:
            responses = boto3.client('ec2', region_name).describe_instance_status(InstanceIds=ids)
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


def installation_finished_in_region(region_name=default_region()):
    '''Checks if installation has finished on all instances in a given region.'''

    results = []
    cmd = "tail -1 setup.log"
    results = run_cmd_in_region(cmd, region_name, output=True)
    for result in results:
        if len(result) < 4 or result[:4] != b'done':
            return False

    print(f'installation in {region_name} finished')
    return True

#======================================================================================
#                              routines for all regions
#======================================================================================

def exec_for_regions(func, regions=use_regions(), parallel=True, pids=None, delay=0):
    '''A helper function for running routines in all regions.'''

    results = []
    if parallel:
        try:
            if pids is None:
                results = Parallel(n_jobs=N_JOBS)(delayed(func)(region_name) for region_name in regions)
            else:
                results = Parallel(n_jobs=N_JOBS)(delayed(func)(region_name, pids=pids[region_name], delay=delay) for region_name in regions)

        except Exception as e:
            print('error during collecting results', type(e), e)
    else:
        for region_name in regions:
            results.append(func(region_name))

    if results and isinstance(results[0], list):
        return [res for res_list in results for res in res_list]

    return results


def launch_new_instances(nppr, instance_type='t2.micro'):
    '''
    Launches n_parties_per_region in ever region from given regions.
    :param dict nppr: dict region_name --> n_parties_per_region
    '''

    regions = nppr.keys()

    failed = []
    print('launching instances')
    for region_name in regions:
        print(region_name, '', end='')
        instances = launch_new_instances_in_region(nppr[region_name], region_name, instance_type)
        if not instances:
            failed.append(region_name)

    tries = 5
    while failed and tries:
        tries -= 1
        sleep(5)
        print('there were problems in launching instances in regions', *failed, 'retrying')
        for region_name in failed.copy():
            print(region_name, '', end='')
            instances = launch_new_instances_in_region(nppr[region_name], region_name, instance_type)
            if instances:
                failed.remove(region_name)

    if failed:
        print('reporting complete failure in regions', failed)


def terminate_instances(regions=use_regions(), parallel=True):
    '''Terminates all instances in ever region from given regions.'''

    return exec_for_regions(terminate_instances_in_region, regions, parallel)


def all_instances(regions=use_regions(), states=['running','pending'], parallel=True):
    '''Returns all running or pending instances from given regions.'''

    return exec_for_regions(partial(all_instances_in_region, states=states), regions, parallel)


def instances_ip(regions=use_regions(), parallel=True):
    '''Returns ip addresses of all running or pending instances from given regions.'''

    return exec_for_regions(instances_ip_in_region, regions, parallel)


def instances_state(regions=use_regions(), parallel=True):
    '''Returns states of all instances in given regions.'''

    return exec_for_regions(instances_state_in_region, regions, parallel)


def send_file(path='cmd/gomel/main.go', regions=use_regions()):
    '''Sends file from specified path to all hosts in given regions.'''

    return exec_for_regions(partial(send_file_in_region, path), regions, True)


def run_task(task='test', regions=use_regions(), parallel=True, output=False, pids=None, delay=0):
    '''
    Runs a task from fabfile.py on all instances in all given regions.
    :param string task: name of a task defined in fabfile.py
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_task_in_region, task, parallel=parallel, output=output), regions, parallel, pids, delay)


def run_cmd(cmd='ls', regions=use_regions(), parallel=True, output=False):
    '''
    Runs a shell command cmd on all instances in all given regions.
    :param string cmd: a shell command that is run on instances
    :param list regions: collections of regions in which the tast should be performed
    :param bool parallel: indicates whether task should be dispatched in parallel
    :param bool output: indicates whether output of task is needed
    '''

    return exec_for_regions(partial(run_cmd_in_region, cmd, output=output), regions, parallel)


def wait(target_state, regions=use_regions()):
    '''Waits until all machines in all given regions reach a given state.'''

    exec_for_regions(partial(wait_in_region, target_state), regions)


#======================================================================================
#                               aggregates
#======================================================================================


def create_images(regions=use_regions(), image_name='gomel'):
    '''Creates images with golang set up for gomel.'''

    base_region = regions[0]
    print('launching a machine')

    init_key_pair(base_region)
    security_group_id = security_group_id_by_region(base_region)
    image_id = image_id_in_region(base_region, 'ubuntu')

    instance = create_instances(base_region, image_id, 1, 't2.micro', 'aleph', security_group_id)[0]


    print('waiting for transition from pending to running')
    wait('running', regions[:1])

    print('waiting till ports are open on machines')
    # this is really slow, and actually machines are ready earlier! refactor
    #wait('ssh ready', regions)
    sleep(120)

    print('installing dependencies')
    # install dependencies on hosts
    run_task_in_region('setup', base_region)
    sleep(300)

    print('creating image in region', base_region)
    image = instance.create_image(
        BlockDeviceMappings=[
            {
                'DeviceName': '/dev/sda1',
                'Ebs': {
                    'DeleteOnTermination': True,
                    'VolumeSize': 8,
                    'VolumeType': 'gp2',
                },
            },
        ],
        Description='image for running gomel experiments',
        Name=image_name,
    )

    print('waiting for image to be available')
    while image.state != 'available':
        print('.', end='')
        sleep(10)
        image.reload()
    print()

    print('terminating the instance')
    instance.terminate()

    print('copying image to remaining regions')
    for region in regions[1:]:
        print(region, end=' ')
        boto3.client('ec2', region).copy_image(
            Name=image.name,
            Description=image.description,
            SourceImageId=image.image_id,
            SourceRegion=base_region
        )

    print('\ndone')

def deregister_image(regions, image_name):
    for r in regions:
        print(r)
        ec2 = boto3.resource('ec2', r)
        images = ec2.images.filter(Filters=[{'Name':'name','Values':[image_name]}])
        for i in images:
            print('   ', i.deregister())

def get_logs_from_region(region, ip2pid, logs_per_region=1, with_prof=False):
    color_print(f'collecting logs in {region}')
    for k, ip in enumerate(instances_ip_in_region(region)):
        if k == logs_per_region:
            return
        pid = ip2pid[ip]
        run_task_for_ip('get-log', [ip], parallel=0, pids=[pid])
        if with_prof and int(pid) % 16 == 0:
            run_task_for_ip('get-profile', [ip], parallel=0, pids=[pid])

def get_logs(regions, name, logs_per_region=1, with_prof=False, pids=None, ip2pid=None):
    '''Retrieves all logs from instances.'''

    if pids is None:
        pids, ip2pid, c = {}, {}, 0
        for r in regions:
            ipl = instances_ip_in_region(r)
            pids[r] = [str(pid) for pid in range(c,c+len(ipl))]
            ip2pid.update({ip:pid for (ip, pid) in zip(ipl, pids[r])})
            c += len(ipl)

    if not os.path.exists('../results'):
        os.makedirs('../results')

    l = len(glob('../results/*'))
    if l:
        print('sth is in dir ../results; aborting')
        return

    Parallel(n_jobs=N_JOBS)(delayed(get_logs_from_region)(region, ip2pid, logs_per_region, with_prof) for region in regions)

    color_print(f'{len(os.listdir("../results"))} files in ../results')

    result_path = f'{name}'

    color_print('move and rename dir')
    shutil.move('../results', result_path)

    color_print('unzip downloaded logs')
    for path in os.listdir(result_path):
        path = os.path.join(result_path, path)
        with zipfile.ZipFile(path, 'r') as zf:
            zf.extractall(result_path)
        os.remove(path)

    color_print('zip the dir with all the files')
    with zipfile.ZipFile(result_path+'.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        # write logs
        for path in os.listdir(result_path):
            path = os.path.join(result_path, path)
            zf.write(path)
            os.remove(path)

        # write pids
        path = os.path.join(result_path, 'pids')
        with open(path, 'w') as f:
            json.dump(pids, f)
        zf.write(path)
        os.remove(path)

        # write repo version
        path = os.path.join(result_path, 'repo.ver')
        with open(path, 'w') as f:
            f.write(check_output('git rev-parse HEAD'.split()).decode())
        zf.write(path)
        os.remove(path)

    os.rmdir(result_path)
    color_print('done')

#======================================================================================
#                                        shortcuts
#======================================================================================

tr = run_task_in_region
t = run_task

cmr = run_cmd_in_region
cm = run_cmd

ti = terminate_instances
tir = terminate_instances_in_region

rs = lambda : run_protocol(7, use_regions(), 't2.micro', False)


#======================================================================================
#                                       run_protocol
#======================================================================================

def run_protocol(n_parties, regions=use_regions(), instance_type='t2.micro', profiler=False, delay=0):
    '''Runs the protocol.'''

    # testnet limit
    assert n_parties <= 8

    start = time()
    parallel = n_parties > 1

    color_print('launching machines')
    nhpr = n_parties_per_regions(n_parties, regions)
    launch_new_instances(nhpr, instance_type)

    color_print('waiting for transition from pending to running')
    wait('running', regions)

    color_print('generating keys&addresses files')
    pids, ip2pid, ip_list, c = {}, {}, [], 0
    for r in regions:
        ipl = instances_ip_in_region(r)
        pids[r] = [str(pid) for pid in range(c,c+len(ipl))]
        ip2pid.update({ip:pid for (ip, pid) in zip(ipl, pids[r])})
        c += len(ipl)
        ip_list.extend(ipl)

    write_addresses(ip_list)
    generate_keys()

    color_print('waiting till ports are open on machines')
    sleep(120)
    # wait('open 22', regions)

    color_print('mkdir')
    run_task('mkdir', regions, parallel)

    color_print('send data: keys, addresses')
    cmd = 'zip -r data.zip data/'
    call(cmd.split())
    run_task('send-data', regions, parallel, False, pids)

    color_print('send the binary')
    run_task('send-binary', regions, parallel)

    color_print('start nginx')
    run_task('run-nginx')

    color_print(f'establishing the environment took {round(time()-start, 2)}s')
    # run the experiment
    if profiler:
        run_task('run-protocol-profiler', regions, parallel, False, pids, time()+delay)
    else:
        run_task('run-protocol', regions, parallel, False, pids, time()+delay)
