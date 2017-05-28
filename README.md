## Wi-Sun_EnergyMeter（ワイサンエナジーメーター） パワーセーブ対応版
Branch power_save

Wi-SUNモジュールを低消費電力で動作させるためのスリープモードを追加しました。
スリープ機能を使用しない場合、Wi-SUNモジュールの消費電力は約25mAですが、約1/1000の30μA程度まで下げることが出来ます。

このブランチは国野亘がyawatajunk/Wi-SUN_EnergyMeter からforkしたものです。
権利については、元ソースにしたがってください。

## 元の回路図からの追加

Raspberry Pi のGPIO23をWi-SUNモジュールのWKUP端子へ接続してください。（スリープからの復帰に必要です。）


元のソースはこちら：
https://github.com/yawatajunk/Wi-SUN_EnergyMeter
