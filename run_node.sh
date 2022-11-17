#!/bin/bash

set -eo pipefail

# The defaults
NAME="aleph-node-$(xxd -l "16" -p /dev/urandom | tr -d " \n" ; echo)"
BASE_PATH="/data"
HOST_BASE_PATH="${HOME}/.alephzero"
DB_SNAPSHOT_FILE="db_backup.tar.gz"
DB_SNAPSHOT_URL="https://db.test.azero.dev/latest.html"
MAINNET_DB_SNAPSHOT_URL="https://db.azero.dev/latest.html"
DB_SNAPSHOT_PATH="chains/testnet/"     # testnet by default
CHAINSPEC_FILE="testnet_chainspec.json"


while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help) # display Help
            Help
            exit;;
        --archivist) # Run as an archivist
            ARCHIVIST=true
            shift;;
        --ip)
            PUBLIC_IP="$2"
            shift 2;;
        --dns)
            PUBLIC_DNS="$2"
            shift 2;;
        -n | --name) # Enter a name
            NAME="$2"
            shift 2;;
        -d | --data_dir) # Choose the data directory
            HOST_BASE_PATH="$2"
            shift 2;;
        --mainnet) # Join the mainnet
            DB_SNAPSHOT_PATH="chains/mainnet/"
            CHAINSPEC_FILE="mainnet_chainspec.json"
            DB_SNAPSHOT_URL="${MAINNET_DB_SNAPSHOT_URL}"
            shift;;
        -i | --image) # Enter a base path
            ALEPH_IMAGE="$2"
            PULL_IMAGE=false
            shift 2;;
        --build_only)
            BUILD_ONLY=true
            shift;;
        --sync_from_genesis)
            SYNC=true
            shift;;
        --stash_account)
            STASH_ACCOUNT=$2
            shift 2;;
        -* | --* )
            echo "Warning: unrecognized option: $1"
            exit;;
        *)
            echo "Unrecognized command"
            Help
            exit;;
  esac
done

if [ -z "${PUBLIC_IP}" ] && [ -z "${PUBLIC_DNS}" ]
then
    echo "You need to provide either a public ip address of your node (--ip) or a public dns address of your node (--dns)."
    exit 1
fi

ALEPH_VERSION=$(cat env/version)

mkdir -p ${HOST_BASE_PATH}
DB_SNAPSHOT_PATH=${HOST_BASE_PATH}/${DB_SNAPSHOT_PATH}
mkdir -p ${DB_SNAPSHOT_PATH}

if [ -z "$ALEPH_IMAGE" ]
then
    echo "Pulling docker image..."
    ALEPH_IMAGE=public.ecr.aws/p6e8q1z1/aleph-node:${ALEPH_VERSION}
fi

if [ -z "$BUILD_ONLY" ]
then
    echo "Running the node..."

    # remove the container if it exists
    if [ "$(docker ps -aq -f status=exited -f name=${NAME})" ]; then
        docker rm ${NAME}
    fi

    if [ -z "$ARCHIVIST" ]
    then
        ###### VALIDATOR ######
        source env/validator
        eval "echo \"$(cat env/validator)\"" > env/validator.env
        ENV_FILE="env/validator.env"

        # setup public addresses
        if [[ -n "${PUBLIC_DNS}" ]]
        then
            PUBLIC_ADDR="/dns4/${PUBLIC_DNS}/tcp/${PORT}"
            PUBLIC_VALIDATOR_ADDRESS="${PUBLIC_DNS}:${VALIDATOR_PORT}"
        else
            PUBLIC_ADDR="/ip4/${PUBLIC_IP}/tcp/${PORT}"
            PUBLIC_VALIDATOR_ADDRESS="${PUBLIC_IP}:${VALIDATOR_PORT}"
        fi

        echo "Running with public P2P address: ${PUBLIC_ADDR}"
        echo "And validator address: ${PUBLIC_VALIDATOR_ADDRESS}."

        PORT_MAP="${PORT}:${PORT}"
        VALIDATOR_PORT_MAP="${VALIDATOR_PORT}":"${VALIDATOR_PORT}"

        docker run --env-file ${ENV_FILE} \
                   --env PUBLIC_ADDR="${PUBLIC_ADDR}" \
                   --env PUBLIC_VALIDATOR_ADDRESS="${PUBLIC_VALIDATOR_ADDRESS}" \
                   -p ${RPC_PORT_MAP} \
                   -p ${WS_PORT_MAP} \
                   -p ${PORT_MAP} \
                   -p ${VALIDATOR_PORT_MAP} \
                   -p ${METRICS_PORT_MAP} \
                   -u $(id -u):$(id -g) \
                   --mount type=bind,source=${HOST_BASE_PATH},target=${BASE_PATH} \
                   --name ${NAME} \
                   --restart unless-stopped \
                   -d ${ALEPH_IMAGE}

    else
        ###### ARCHIVIST #######
        source env/archivist
        eval "echo \"$(cat env/archivist)\"" > env/archivist.env
        ENV_FILE="env/archivist.env"

        if [[ -n "${PUBLIC_DNS}" ]]
        then
            PUBLIC_ADDR="/dns4/${PUBLIC_DNS}/tcp/${PORT}"
        else
            PUBLIC_ADDR="/ip4/${PUBLIC_IP}/tcp/${PORT}"
        fi

        echo "Running with public P2P address: ${PUBLIC_ADDR}"

        PORT_MAP="${PORT}:${PORT}"

        docker run --env-file ${ENV_FILE} \
                   --env PUBLIC_ADDR="${PUBLIC_ADDR}" \
                   -p ${RPC_PORT_MAP} \
                   -p ${WS_PORT_MAP} \
                   -p ${PORT_MAP} \
                   -p ${METRICS_PORT_MAP} \
                   -u $(id -u):$(id -g) \
                   --mount type=bind,source=${HOST_BASE_PATH},target=${BASE_PATH} \
                   --name ${NAME} \
                   --restart unless-stopped \
                   -d ${ALEPH_IMAGE}
    fi
fi
