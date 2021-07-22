# Aleph-Testnet

Aleph Zero Blockchain python scripts for running TestNet and DevNet.

# Usage instructions

- Create an account on AWS, set up credentials, and a default region as described [here](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration).
- Put keys for ssh in key_pairs.
- Install packages needed for orchestrating experiments: GNU parallel, zip, unzip and Python 3 packages: fabric, boto3, ipython, tqdm, matplotlib.
- Then, run `ipython -i shell.py`. This opens a shell with procedures orchestrating experiments.
  The main procedures are `run_protocol(n_processes, regions, instance_type)` and
  `run_devnet(n_processes, regions, instance_type)` that run `n_processes` spread
  uniformly across specified `regions` using EC2 machines of `instance_type`. E.g.
  `run_devnet(4, ['eu-west-1'], 't2.micro')`.
- `run_task('some-task', regions)` procedure calls the task `some_task` defined in `fabfile.py` for all machines in given
  regions, note the change `s/-/_`,
- `run_cmd(shell_cmd, regions)` dispatches the `shell_cmd` on all machines in given regions.
- To terminate instances run `terminate_instances(regions)`.
