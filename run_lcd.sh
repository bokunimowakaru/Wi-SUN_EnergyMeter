#!/bin/bash
sudo kill `pidof -x sem_com.py` &> /dev/null
sudo kill `pidof -x raspi_lcd.sh` &> /dev/null
sleep 3
nohup ./sem_com.py 2> error.log > sem_com.log &
nohup ./raspi_lcd.sh &> raspi_lcd.log &
echo "done"
