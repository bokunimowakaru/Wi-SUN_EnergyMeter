#!/bin/bash
sudo kill `pidof -x sem_com.py` &> /dev/null
sleep 3
nohup ./sem_com.py < /dev/null &> sem_com.log &
echo "done"
