#!/bin/bash


## Now we will attempt to check validator's session keys
CLIAIN_IMAGE='public.ecr.aws/p6e8q1z1/cliain:latest'
CLIAIN_ENDPOINT='wss://ws.test.azero.dev/'
JQ_IMAGE='stedolan/jq:latest'
RPC_PORT='9933'

# Pull cliain from ecr
docker pull "${CLIAIN_IMAGE}"

# Try to retrieve set session keys from chain's storage
CLIAIN_NAME="cliain-$(xxd -l "16" -p /dev/urandom | tr -d " \n" ; echo)"

NEW_KEYS_JSON=$(curl -H "Content-Type: application/json" -d '{"id":1,
            "jsonrpc":"2.0", "method": "author_rotateKeys"}' http://127.0.0.1:"${RPC_PORT}")

NEW_KEYS=$(echo ${NEW_KEYS_JSON} | docker run -i "${JQ_IMAGE}" '.result' | tr -d '"')
echo "New session keys: ${NEW_KEYS}"

docker run --rm --name="${CLIAIN_NAME}" -i "${CLIAIN_IMAGE}" --node "${CLIAIN_ENDPOINT}" --seed "$1" set-keys --new-keys "${NEW_KEYS}"
