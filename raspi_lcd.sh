#!/bin/bash
#
# Copyright (c) 2017-2019 Wataru KUNINO
#
# run_lcd.sh から自動起動されるスクリプトです。
# README.mdならびにrun_lcd.shを参照ください。

/home/pi/RaspberryPi/gpio/raspi_gpo 24 1
sleep 6
/home/pi/RaspberryPi/gpio/raspi_lcd -i -r24 `hostname -I|cut -d" " -f1`

date > raspi_lcd.log
next_time=$(( SECONDS + 600 ))
while true; do
	LCD=`tail -1 sem_com.log`
	if [ -n "${LCD}" ]; then
		if [ $SECONDS -gt $next_time ]; then
			/home/pi/RaspberryPi/gpio/raspi_lcd -i -r24 "${LCD}" &>> raspi_lcd.log &
			next_time=$(( SECONDS + 600 ))
		else
			/home/pi/RaspberryPi/gpio/raspi_lcd -i "${LCD}" &>> raspi_lcd.log &
		fi
	fi
	sleep 6
done
