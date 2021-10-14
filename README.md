# Aleph-Testnet

Aleph Zero Blockchain python scripts for running TestNet and DevNet.

# Usage instructions

- Create an account on AWS, set up credentials, and a default region as described [here](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration).
- Put keys for ssh in key_pairs (both the private key e.g. `aleph.pem` and its fingerprint (`aleph.fingerprint`))
- Put SSL certificates in the nginx/cert directory (`self-signed.crt` and `self-signed.key`)
- Make sure you have the aleph node binary inside a bin directory (needed for committee key generation step, `cp <...>/aleph-node/target/release/aleph-node bin/`)
- Install packages needed for orchestrating experiments: GNU parallel, fabric, zip, unzip and Python 3 packages (with `pip install -r requirements.txt`).
- Then, run `ipython -i shell.py`. This opens a shell with procedures orchestrating experiments.
  The main procedure is `setup_nodes(n_processes, chain_type, regions, instance_type, volume_size, tag)` that prepares the `n_processes` spread
  uniformly across specified `regions` using EC2 machines of `instance_type`. E.g.
  `setup_nodes(4, 'dev', ['eu-west-1'], 't2.micro', 8, 'my_devnet')`.
  After it succeeds, the `dispatch` task has to be run.
- `run_task('some-task', tag=tag)` procedure calls the task `some_task` defined in `fabfile.py` for all machines that was created with the tag, note the change `s/-/_`,
- `run_cmd(shell_cmd, tag)` dispatches the `shell_cmd` on all machines.
- To terminate instances run `ti(tag)`.

# TODOs

- dockerize nginx ([nginx-proxy](https://github.com/nginx-proxy/nginx-proxy))
- add [letsencrypt(https://github.com/nginx-proxy/acmenhu-companion)] bot image to obtain real SSL certificates (requires moving DNS to AWS)
