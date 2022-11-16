#!/bin/bash

smee_key=$1
appid=$2
appsecret="$3"
port=5000

# Start the first process
smee -u https://smee.io/$1 --port $port &
  
# Start the second process
python app.py --port $port --id "$appid" --secret "$appsecret" &
  
# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
