#!/bin/zsh

set -e

addrs=($(bat -p addresses))

for i in $(seq 0 9); do
    a=$addrs[$((i+1))]
    echo $i $a
    ssh -o "StrictHostKeyChecking no" -i key_pairs/aleph.pem ubuntu@$a -t 'cd aleph-node-runner && pwd && ./run_node.sh --name Node'$i' --ip '$a' --mainnet --sync_from_genesis'
done
