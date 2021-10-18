#!/bin/bash

set -e

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.37.2/install.sh | bash # install node version manager

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
echo installed nvm > setup_flooder.log

git clone -b for_testnet-rebased https://github.com/fixxxedpoint/sub-flood.git
echo cloned repo >> setup_flooder.log
cd sub-flood

nvm install
nvm use
echo installed dependencies >> ../setup_flooder.log

npm install yarn
echo installed yarn >> ../setup_flooder.log

npm run build
echo built >> ../setup_flooder.log
