#!/bin/bash
sudo kill `pidof -x sem_com.py` &> /dev/null
sleep 3
nohup ./sem_com.py 2> error.log | tee sem_com.log | /home/pi/RaspberryPi/gpio/raspi_lcd -f -r24 &> lcd.log &
echo "done"
