#!/bin/bash
#
# Copyright (c) 2017-2019 Wataru KUNINO
#
# /etc/rc.localへ下記を追加すると自動的に起動する
#       cd /home/pi/Wi-SUN_EnergyMeter/
#       ./stopByGPIO27.sh &
#       sleep 2
#       ./run_lcd.sh &

sudo kill `pidof -x sem_com.py` &> /dev/null
sudo kill `pidof -x raspi_lcd.sh` &> /dev/null
sleep 3
nohup ./sem_com.py 2> error.log > sem_com.log &
nohup ./raspi_lcd.sh &> raspi_lcd.log &
echo "done"

CHECK_PREV=""
while true; do
	sleep 180
	CHECK=`tail -1 sem_com.log`
	if [ -n "${CHECK}" ]; then
		if [ "${CHECK}" = "${CHECK_PREV}" ] ; then
			sudo kill `pidof -x sem_com.py` &> /dev/null
			sudo kill `pidof -x raspi_lcd.sh` &> /dev/null
			sleep 10
			nohup ./sem_com.py 2>> error.log >> sem_com.log &
			nohup ./raspi_lcd.sh &>> raspi_lcd.log &
		fi
	fi
	CHECK_PREV=${CHECK}
done
