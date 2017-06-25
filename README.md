## Wi-Sun_EnergyMeter（ワイサンエナジーメーター） パワーセーブ対応版

Wi-SUNモジュールを低消費電力で動作させるためのスリープモードを追加しました。
スリープ機能を使用しない場合、Wi-SUNモジュールの消費電力は約25mAですが、約1/1000の30μA程度まで下げることが出来ます。

このブランチ(power_save)は国野亘がyawatajunk/Wi-SUN_EnergyMeter からforkしたものです。
権利については、元ソースにしたがってください。

	Branch: power_save


## 元の回路図からの追加点と実行方法

Raspberry Pi のGPIO23をWi-SUNモジュールのWKUP端子へ接続してください。（スリープからの復帰に必要です。）
また、本ソフトウェアを cloneし、run.shを実行してください。

	git clone https://github.com/bokunimowakaru/Wi-SUN_EnergyMeter.git
	cd ~/Wi-SUN_EnergyMeter
	./run.sh

他にPhython用のシリアルドライバなどの追加が必要となる場合があります。うまく、動かないときは後述の「基本動作の確認」を参照してください。


## I2C小型液晶AQM0802を使用する場合

I2C信号,電源3.3V,GND,RESET信号を接続してください。RESET信号はRaspberry PiのGPIO24へ接続してください。
また、下記のドライバをインストールし、run_lcd.shを実行してください。

	git clone https://github.com/bokunimowakaru/RaspberryPi.git
	cd RaspberryPi/gpio
	make
	cd ~/Wi-SUN_EnergyMeter
	./run_lcd.sh


## 基本動作の確認

原作者(yawatajunkさん)が作成した詳しい説明書をご覧ください。

Branch patch-1: https://github.com/bokunimowakaru/Wi-SUN_EnergyMeter/tree/patch-1
	(認証時の不具合修正版)


# 元のソースの所在

以下に元のソースコードを保存しています。

Branch master: https://github.com/bokunimowakaru/Wi-SUN_EnergyMeter/tree/master
	(This branch is even with yawatajunk:master. )

原作者のページ: https://github.com/yawatajunk/Wi-SUN_EnergyMeter

以上
