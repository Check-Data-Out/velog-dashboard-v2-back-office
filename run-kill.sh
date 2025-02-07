#!/bin/bash

# 운영계에서만 사용할 script
# chmod +x run.sh

pkill -9 -ef "gunicorn"
echo "====================== process kill clear, check out the result ======================"
sleep 1
