#!/bin/zsh

set -e

addrs=($(bat -p addresses))
sed -i 's@BOOT_NODES.*@BOOT_NODES=/ip4/'$addrs[1]'/tcp/30333/p2p/12D3KooWHZMfomKa3Q9LQxS75AK75wDY8BHoYjMUvDmQRDRZDJtC@' shelter/validator
for i in $(seq 0 9); do
    a=$addrs[$((i+1))]
    echo $i $a
    scp -o "StrictHostKeyChecking no" -i key_pairs/aleph.pem shelter/validator ubuntu@$a:/home/ubuntu/aleph-node-runner/env
    scp -o "StrictHostKeyChecking no" -i key_pairs/aleph.pem shelter/run_node.sh ubuntu@$a:/home/ubuntu/aleph-node-runner/
    scp -o "StrictHostKeyChecking no" -i key_pairs/aleph.pem shelter/p2p/p2p$i ubuntu@$a:/home/ubuntu/.alephzero/p2p_secret
    scp -o "StrictHostKeyChecking no" -i key_pairs/aleph.pem shelter/keys/v$i/* ubuntu@$a:/home/ubuntu/.alephzero/chains/mainnet/keystore
done
