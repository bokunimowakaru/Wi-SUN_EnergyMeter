#!/bin/bash
#
# Apple Pi DEMO
#
# Copyright (c) 2017 Wataru KUNINO
#
# /etc/rc.localへ下記を追加すると自動的に起動する
#       /home/pi/RaspberryPi/gpio/apple_pi.sh &

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
