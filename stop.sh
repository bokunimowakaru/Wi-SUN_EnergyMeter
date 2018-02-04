#!/bin/bash
sudo kill `pidof -x sem_com.py` &> /dev/null
sudo kill `pidof -x raspi_lcd.sh` &> /dev/null
sleep 3
echo "done"
