#!/bin/bash

echo install dependencies >> docker_setup.log
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    software-properties-common \
    docker.io

echo configure docker >> docker_setup.log
sudo gpasswd -a "${USER}" docker
sudo systemctl start docker
sudo systemctl enable docker

echo install docker-compose >> docker_setup.log
sudo curl -L "https://github.com/docker/compose/releases/download/1.27.4/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod a+x /usr/local/bin/docker-compose

echo done >> docker_setup.log
