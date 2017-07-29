#!/bin/bash
gpio -g mode 27 in
gpio -g mode 27 up
while true; do
IN=`gpio -g read 27`
if [ $IN = "0" ]; then
	/home/pi/RaspberryPi/gpio/raspi_lcd -i "shuting down..."
	sleep 2
	IN=`gpio -g read 27`
	if [ $IN = "0" ]; then
		kill `pidof -x sem_com.py` &> /dev/null
		sleep 1
		/home/pi/RaspberryPi/gpio/raspi_lcd -i "Killed  sem_com"
		sleep 3
		/home/pi/RaspberryPi/gpio/raspi_lcd -i "Bye."
		sudo shutdown -h now
		echo "done"
		exit 0
	fi
	/home/pi/RaspberryPi/gpio/raspi_lcd -i "Canceled"
fi
sleep 5
done
