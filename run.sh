#!/bin/bash
kill `pidof -x sem_com.py` &> /dev/null
sleep 3
nohup ./sem_com.py < /dev/null > /dev/null 2> error.log &
echo "done"
