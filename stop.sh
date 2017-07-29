#!/bin/bash
kill `pidof -x sem_com.py` &> /dev/null
sleep 3
echo "done"
