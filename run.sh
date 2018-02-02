#!/bin/bash
sudo kill `pidof -x sem_com.py` &> /dev/null
sleep 3
nohup ./sem_com.py 2> error.log > sem_com.log &
echo "done"
