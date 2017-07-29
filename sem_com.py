#!/usr/bin/python3
# coding: UTF-8

# 24時間でPANA認証が切れて通信が出来なくなる　2度目に失敗するみたい


import argparse
import binascii
import datetime
import glob
import json
import threading
import time
import os
import pickle
import socket
import sys

import RPi.GPIO as gpio
from y3module import Y3Module
from echonet_lite import *
import user_conf


# 定数定義
Y3RESET_GPIO = 18						# Wi-SUNリセット用GPIO
Y3WKUP_GPIO = 23						# Wi-SUN起動用GPIO
LED_GPIO = 4							# LED用GPIO
LCD_LOG = True							# LCD表示用(8桁2行)の短いログ出力
PAC_LIFETIME = 12 * 60 * 60				# PANAクライアントの認証間隔

# ログファイル関連
TMP_LOG_DIR = 'logs/tmp/'				# 一次ログディレクトリ
LOG_DIR = 'logs/csv/'					# ログ用ディレクトリ, 本スクリプトからの相対パス
SOCK_FILE = TMP_LOG_DIR + 'sem.sock'	# UNIXソケット
DEVICE = 'meter_1,' 					# UDP送信用デバイス名 8文字
TMP_LOG_FILE = TMP_LOG_DIR + 'sem.csv'	# 一時ログファイル

POW_DAYS_JSON_FILE = LOG_DIR + 'pow_days.json'	# JSON形式の電力ログファイル
POW_DAY_LOG_HEAD = 'pow_day_'			# 日別ログファイル名の先頭
POW_DAY_LOG_FMT = '%Y%m%d'				#		 日時フォーマット

# 低圧スマート電力量計 情報保存用リスト
sem_info = {}


def gpio_init():
	"""GPIO初期化"""
	gpio.setwarnings(False)
	gpio.setmode(gpio.BCM)

	gpio.setup(Y3RESET_GPIO, gpio.OUT)
	gpio.setup(Y3WKUP_GPIO, gpio.OUT)
	gpio.setup(LED_GPIO, gpio.OUT)

	gpio.output(Y3WKUP_GPIO, gpio.HIGH)
	time.sleep(0.1)
	gpio.output(Y3RESET_GPIO, gpio.HIGH)

	gpio.output(LED_GPIO, gpio.LOW)


class LedThread(threading.Thread):
	"""LEDを点滅させるスレッド"""
	def __init__(self):
		super().__init__()
		self._trigger = False
		self._termFlag = False

	def run(self):
		while not self._termFlag:
			if self._trigger:
				self.ledon(True)
				time.sleep(0.3)
				self.ledon(False)
				self._trigger = False
			else:
				time.sleep(0.1)

	@staticmethod
	def ledon(ctl):
		if ctl:
			gpio.output(LED_GPIO, gpio.HIGH)
		else:
			gpio.output(LED_GPIO, gpio.LOW)

	def oneshot(self):
		self._trigger = True

	def terminate(self):
		self._termFlag = True
		self.join()


def y3reset():
	"""Wi-Sunモジュールのリセット"""
	gpio.output(Y3RESET_GPIO, gpio.LOW)    # high -> low -> high
	time.sleep(0.5)
	gpio.output(Y3RESET_GPIO, gpio.HIGH)
	time.sleep(2.0)

def y3wakeup():
	"""Wi-Sunモジュールのスリープ復帰"""
	gpio.output(Y3WKUP_GPIO, gpio.LOW)	   # high -> low -> high
	time.sleep(0.1)
	gpio.output(Y3WKUP_GPIO, gpio.HIGH)
	time.sleep(0.2)

class Y3ModuleSub(Y3Module):
	"""Y3Module()のサブクラス"""
	global sem_inf_list
	
	def __init__(self):
		super().__init__()
		self.EHD = '1081'
		self.ECV_INF = '73'   # ECHONET ECVコード　（INF)
	
	# UART受信スレッドrun()をECHONET Lite電文用に拡張
	#	UART受信用スレッド
	def run(self):
		while not self.term_flag:
			msg = self.read()
			if msg:
				msg_list = self.parse_message(msg)

				# sys.stdout.write('[MSG]: {}\n'.format(msg_list))			 # 全受信データ（リスト化済み）表示 DEBUG
				# UDP(PANA)の受信
				if msg_list['COMMAND'] == 'ERXUDP' and msg_list['LPORT'] == self.Y3_UDP_PANA_PORT:
					if LCD_LOG:
						sys.stdout.write('PANA    ERXUDP\n')
					else:
						sys.stdout.write('[PANA]: {}\n'.format(msg_list['DATA']))
				# スマートメーターが自発的に発するプロパティ通知
				if msg_list['COMMAND'] == 'ERXUDP' and msg_list['DATA'][0:4] == self.EHD \
							and msg_list['DATA'][20:22] == self.ECV_INF:
					sem_inf_list.append(msg_list)
					if LCD_LOG:
						sys.stdout.write('PANA    appended\n')
					else:
						sys.stdout.write('[PANA]: appended {}\n'.format(msg_list))
				elif self.search['search_words']:	  # サーチ中である
					# サーチワードを受信した。
					search_words = self.search['search_words'][0]
					if isinstance(search_words, list):
						for word in search_words:
							if msg_list['COMMAND'].startswith(word):
								self.search['found_word_list'].append(msg_list)
								self.search['search_words'].pop(0)
								break
					elif msg_list['COMMAND'].startswith(search_words):
						self.search['found_word_list'].append(msg_list)
						self.search['search_words'].pop(0)
					
					elif self.search['ignore_intermidiate']:
						pass	# 途中の受信データを破棄 
				
					else:	 # サーチワードではなかった
						self.enqueue_message(msg_list)
				
				else:	# サーチ中ではない
					self.enqueue_message(msg_list)
				
			elif self.search['timeout']:  # read()がタイムアウト，write()でタイムアウトが設定されている
				if time.time() - self.search['start_time'] > self.search['timeout']:
					self.search['found_word_list'] = []
					self.search['search_words'] = []
					self.search['timeout'] = 0


def sem_get(epc):
	"""プロパティ値要求 'Get' """
	global tid_counter
	
	frame = sem.GET_FRAME_DICT['get_' + epc]
	tid_counter = tid_counter + 1 if tid_counter + 1 != 65536 else 0  # TICカウントアップ
	frame = sem.change_tid_frame(tid_counter, frame)
	res = y3.udp_send(1, ip6, True, y3.Y3_UDP_ECHONET_PORT, frame)


def sem_get_getres(epc):
	"""プロパティ値要求 'Get', 'GetRes'受信
		epc: EHONET Liteプロパティ
	"""
	sem_get(epc)	# 'Get'送信
	start = time.time()
	
	while True:
		if y3.get_queue_size(): 	# データ受信
			msg_list = y3.dequeue_message() # 受信データ取り出し
			if msg_list['COMMAND'] == 'ERXUDP':
				parsed_data = sem.parse_frame(msg_list['DATA'])
				if parsed_data['tid'] != tid_counter:
					errmsg = '[Error]: ECHONET Lite TID mismatch\n'
					sys.stderr.write(errmsg)
					return False
				else:
					return msg_list['DATA']
			else:
				sys.stderr.write('[Error]: Unknown data received.\n')
				return False

		else:	# データ未受信
			if time.time() - start > 20:	# タイムアウト 20s
				sys.stderr.write('[Error]: Time out. @get_getres\n')
				return False
			time.sleep(0.01)


def sem_seti(epc, edt):
	"""プロパティ値書き込み要求（応答要） 'SetI'
		---------------------------------
		　(注)未検証　(注)未検証　(注)未検証
		---------------------------------
		epc: Echonet Liteプロパティ(bytes)
		edt: Echonet Liteプロパティ値データ(bytes)
		return: True(成功) / False(失敗)"""
	
	global tid_counter
	
	tid_counter = tid_counter + 1 if tid_counter + 1 != 65536 else 0  # TICカウントアップ
	ptys = [[epc, edt]]
	frame = sem.make_frame(tid_counter, sem.ESV_CODE['setc'], ptys)
	res = y3.udp_send(1, ip6, True, y3.Y3_UDP_ECHONET_PORT, frame)
	
	start = time.time()

	while True:
		if y3.get_queue_size(): 	# データ受信
			msg_list = y3.dequeue_message() # 受信データ取り出し
			if msg_list['COMMAND'] == 'ERXUDP':
				parsed_data = sem.parse_frame(msg_list['DATA'])
				if parsed_data['tid'] != tid_counter:
					errmsg = '[Error]: ECHONET Lite TID mismatch\n'
					sys.stderr.write(errmsg)
					return False
				else:
					return msg_list['DATA']
			else:
				sys.stderr.write('[Error]: Unknown data received.\n')
				return False

		else:	# データ未受信
			if time.time() - start > 20:	# タイムアウト 20s
				sys.stderr.write('[Error]: Time out. @seti\n')
				return False
			time.sleep(0.01)


def pow_logfile_init(dt):
	"""電力ログファイル初期設定"""
	f = open(TMP_LOG_FILE , 'w')	# 一時ログ初期化
	f.close()

	if not (os.path.isdir(LOG_DIR) and os.access(LOG_DIR, os.W_OK)):	# ログ用ディレクトリ確認
		return False
		
	csv_day_files = []	# 10日分のログファイルリスト(CSV)
	pkl_day_files = []	#						(pickle)
	
	for i in range(10): 	# 10日分の電力ログ作成
		t = dt - datetime.timedelta(days = i)	# 対象日のdatetime
		
		# ログファイル名
		dt_str = t.strftime(POW_DAY_LOG_FMT)
		csv_filename = LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.csv'
		pkl_filename = TMP_LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.pickle'
		
		csv_day_files.append(csv_filename)
		pkl_day_files.append(pkl_filename)
		
		if not os.path.exists(csv_filename):	# 電力ログ(CSV)が無かったら作成する
			try:
				fcsv = open(csv_filename, 'w')
				fcsv.close()
			except:
				return False
		
		if not os.path.exists(pkl_filename):	# 電力ログ(pickle)が無かったら作成する
			result = csv2pickle(csv_filename, pkl_filename)
			if not result:
				return False	   

	files = glob.glob(LOG_DIR + POW_DAY_LOG_HEAD + '*.csv') 		# 電力ログ(CSV)検索
	for f in files:
		if f in csv_day_files:
			continue
		else:
			os.remove(f)	# 古い電力ログ(CSV)を削除

	files = glob.glob(TMP_LOG_DIR + POW_DAY_LOG_HEAD + '*.pickle')	# 電力ログ(pickle)検索
	for f in files:
		if f in pkl_day_files:
			continue
		else:
			os.remove(f)	# 古い電力ログ(pickle)を削除

	# CSVファイルをJSONファイルに変換
	pickle2json(sorted(pkl_day_files), POW_DAYS_JSON_FILE)
	
	return True


def pow_logfile_maintainance(last_dt, new_dt):
	"""電力ログファイル更新"""	  
	if last_dt.minute != new_dt.minute and new_dt.minute % 10 == 0: # 10分毎
		dt_str = last_dt.strftime(POW_DAY_LOG_FMT)

		today_csv_file = LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.csv'
		today_pkl_file = TMP_LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.pickle'
		
		file_cat(today_csv_file, TMP_LOG_FILE)
		os.remove(TMP_LOG_FILE) 		# 一時ログファイルを削除
		
		csv2pickle(today_csv_file, today_pkl_file)	# pickle更新

		if last_dt.day != new_dt.day:	# 日付変更
			pow_logfile_init(new_dt)	# 電力ログ初期化

		else:
			pkl_day_files = glob.glob(TMP_LOG_DIR + POW_DAY_LOG_HEAD + '*.pickle')	 # 電力ログ(pickle)検索
			pickle2json(sorted(pkl_day_files), POW_DAYS_JSON_FILE)	   # CSVファイルをJSONファイルに変換


def file_cat(file_a, file_b):
	"""ファイルを連結する"""
	try:
		fp_a = open(file_a, 'ab')
		fp_b = open(file_b, 'rb')
		fp_a.write(fp_b.read())
		fp_a.close()
		fp_b.close()
		return True
	except:
		return False


def csv2pickle(csvfile, pklfile):
	"""csvファイルをpickleファイルに変換"""
	try:
		fcsv = open(csvfile, 'r')
		fpkl = open(pklfile, 'wb')
		data = fcsv.readlines()
	except:
		return False
		
	if data == []:		# 日付変更時でcsvファイルが空の場合
		dt = datetime.date.today()	  # 現時刻から、0時0分のタイムスタンプを作成
		ts_origin = datetime.datetime.combine(dt, datetime.time(0, 0)).timestamp()
	else:
		ts = int(data[0].strip().split(',')[0]) 	# ログからタイムスタンプを取得
		dt = datetime.datetime.fromtimestamp(ts)	# 0時0分のタイムスタンプを作成
		ts_origin = datetime.datetime(dt.year, dt.month, dt.day).timestamp()

	data_work = [[None, []] for row in range(60 * 24)]	# 作業用空箱
	
	for minute in range(60 * 24):
		data_work[minute][0] = ts_origin + 60 * minute	# 1分刻みのタイムスタンプを設定

	for row in data:
		row_list = row.strip().split(',')	# [タイムスタンプ(s), 電力]
		if row_list[1] != 'None':
			minute = int((int(row_list[0]) - ts_origin) / 60)	# 00:00からの経過時間[分]
			if minute > 0 and minute < 60 * 24: 
				data_work[minute][1].append(int(row_list[1]))	# 電力を追加

	data_summary = [[None, None] for row in range(60 * 24)] # 集計用空箱
	for minute, data in enumerate(data_work):
		data_summary[minute][0] = data[0]
		if len(data[1]):
			data_summary[minute][1] = round(sum(data[1]) / len(data[1]))	# 電力平均値
	
	pickle.dump(data_summary, fpkl)
	
	fcsv.close()
	fpkl.close()

	return True


def pickle2json(pklfiles, jsonfile):
	"""pickleファイルをJSONファイルに変換する"""
	data = []
	for fpkl in pklfiles:
		try:
			f = open(fpkl, 'rb')
			d = pickle.load(f)
			data = data + d
		except:
			return False

	json_data = []		  
	for row in data:
		row = [int(row[0])*1000, None if row[1] is None else int(row[1])]
		json_data.append(row)
			
	s = json.dumps(json_data)
	
	try:
		f = open(jsonfile, 'w')
		f.write(s)
		f.close()
		return True
	except:
		return False


# コマンドライン引数
def arg_parse():
	p = argparse.ArgumentParser()
	p.add_argument('-d', '--delay', help='This script starts after a delay of [n] seconds.', default=0, type=int)
	args = p.parse_args()
	return args


# メイン部
if __name__ == '__main__':

	args = arg_parse()
	if args.delay:	# スクリプトをスタートするまでの待ち時間。sem_appとの連携時にsem_com.pyのスタートを遅らせる。
		if isinstance(args.delay, int):
			ws = args.delay
			if LCD_LOG:
				sys.stdout.write('Waiting for {} s\n'.format(ws))
			else:
				sys.stdout.write('Waiting for {} seconds...\n'.format(ws))
			time.sleep(ws)

	os.chdir(os.path.dirname(os.path.abspath(__file__)))
		
	sem_inf_list = []		# スマートメータのプロパティ通知用
	tid_counter = 0 		# TIDカウンタ
	
	pana_ts = 0.0			# 次回のPANA認証時刻を保持
	saved_dt = datetime.datetime.now()		# 現在日時を保存

	if LCD_LOG:
		sys.stdout.write('SET UP  LogFiles\n')
	else:
		sys.stdout.write('Log files setup...\n')
	result = pow_logfile_init(saved_dt) 	# ログファイル初期化
	
	if not result:
		sys.stderr.write('[Error]: Log file error\n')
		sys.exit(-1)

	gpio_init()

	led = LedThread()
	led.start()
	led.oneshot()

	y3 = Y3ModuleSub()
	y3.uart_open(dev='/dev/ttyAMA0', baud=115200, timeout=1)
	y3.start()
	if LCD_LOG:
		sys.stdout.write('Wi-SUN  SET UP\n')
	else:
		sys.stdout.write('Wi-SUN reset...\n')

	y3reset()
	y3.set_echoback_off()
	y3.set_auto_pac
	y3.set_opt(True)
	y3.set_password(user_conf.SEM_PASSWORD)
	y3.set_routeb_id(user_conf.SEM_ROUTEB_ID)

	sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
	try:
		sock.connect(SOCK_FILE)
	except:
		sock = None

	if user_conf.SOCK_PORT:
		sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	else:
		sock_udp = None

	channel_list = []
	sem_exist = False

	for i in range(10):
		if LCD_LOG:
			sys.stdout.write('SET UP  Scan {}\n'.format(i+1))
		else:
			sys.stdout.write('({}/10) Active scan with a duration of {}...\n'.format(i+1, user_conf.SEM_DURATION))
		channel_list = y3.active_scan(user_conf.SEM_DURATION)
		if channel_list is False:	# active_scan()をCtrl+cで終了したとき
			break
		if channel_list:
			sem_exist = True
			break
	
	if not sem_exist:	# スキャン失敗
		sys.stderr.write('[Error]: Can not connect to a smart energy meter\n')

	if sem_exist:
		ch = channel_list[0]

		if LCD_LOG == False:
			print(ch)
			sys.stdout.write('Energy Meter: [Ch.0x{:02X}, Addr.{}, LQI.{}, PAN.0x{:04X}]\n'.format(ch['Channel'],
							 ch['Addr'], ch['LQI'], ch['Pan ID']))

		# チャンネル設定
		y3.set_channel(ch['Channel'])
		if LCD_LOG == False:
			sys.stdout.write('Set channel to 0x{:02X}\n'.format(ch['Channel']))

		# スマートメータのIP6アドレス
		ip6 = y3.get_ip6(ch['Addr'])
		if LCD_LOG == False:
			sys.stdout.write('IP6 address is \'{}\'\n'.format(ip6))

		# PAN ID
		y3.set_pan_id(ch['Pan ID'])
		if LCD_LOG == False:
			sys.stdout.write('Set PAN ID to 0x{:04X}\n'.format(ch['Pan ID']))

		# PANA認証(PaC)
		sem_exist = False
		pana_done = False
		for i in range(10):
			if LCD_LOG:
				sys.stdout.write('Connect {}\n'.format(i+1))
			else:
				sys.stdout.write('({}/10) PANA connection...\n'.format(i+1))
			sem_exist = y3.start_pac(ip6)
			
			if sem_exist:		# インスタンスリスト通知の受信待ち
				st = time.time()
				while True:
					if sem_inf_list:
						pana_ts = time.time() + PAC_LIFETIME	# 次回の認証時刻を保存(12時間後)
						# pana_ts = time.time() + 120				# 120秒後(デバッグ用)
						if LCD_LOG:
							sys.stdout.write('Connect done.\n')
						else:
							sys.stdout.write('Successfully done.\n')
						time.sleep(3)
						pana_done = True
						break
					elif time.time() - st > 15: 	# PANA認証失敗によるタイムアウト
						sys.stderr.write('Fail to connect.\n')
						sem_exist = False
						pana_done = False
						break
					else:
						time.sleep(0.1)
			
			if pana_done:
				break
			
	if sem_exist:
		sem = EchonetLiteSmartEnergyMeter()
				
		get_list = ['operation_status', 'location', 'version', 'fault_status',
					'manufacturer_code', 'production_no',
					'current_time', 'current_date', 
					'get_pty_map', 'set_pty_map', 'chg_pty_map',
					'epc_coefficient', 'digits', 'unit_amount_energy', 'amount_energy_normal',
					'recent_amount_energy_norm', 'hist_amount_energy1_norm']
					
		for epc in get_list:	# 各種データ取得
			edt = False
			for i in range(10):
				data = sem_get_getres(epc)
				if data:
					parsed_data = sem.parse_frame(data)
					edt = parsed_data['ptys'][0]['edt']
					break
				else:	# Get失敗 再試行
					continue
			
			if parsed_data:
				if epc == 'operation_status':
					result = True if edt == b'\x30' else False

				elif epc == 'location':
					result = binascii.b2a_hex(edt)
					
				elif epc == 'version':
					result = edt[2:3].decode()
					
				elif epc == 'manufacturer_code':
					result = binascii.b2a_hex(edt)

				elif epc == 'production_no':
					result = binascii.b2a_hex(edt)
				   
				elif epc == 'current_time':
					hour = int.from_bytes(edt[0:1], 'big')
					min = int.from_bytes(edt[1:2], 'big')
					result = datetime.time(hour, min)

				elif epc == 'current_date':
					year = int.from_bytes(edt[0:2], 'big')
					month = int.from_bytes(edt[2:3], 'big')
					day = int.from_bytes(edt[3:4], 'big')
					result = datetime.date(year, month, day)

				elif epc == 'fault_status':
					result = True if edt == b'\x42' else False

				elif epc == 'get_pty_map':
					result = binascii.b2a_hex(edt)

				elif epc == 'set_pty_map':
					result = binascii.b2a_hex(edt)

				elif epc == 'chg_pty_map':
					result = binascii.b2a_hex(edt)

				elif epc == 'epc_coefficient':
					result = int.from_bytes(edt, 'big')

				elif epc == 'digits':
					result = int.from_bytes(edt, 'big')

				elif epc == 'unit_amount_energy':
					if edt == b'\x00':
						result = 1.0
					elif edt == b'\x01':
						result = 0.1
					elif edt == b'\x02':
						result = 0.01
					elif edt == b'\x03':
						result = 0.001
					elif edt == b'\x04':
						result = 0.0001
					elif edt == b'\x0A':
						result = 10.0
					elif edt == b'\x0B':
						result = 100.0
					elif edt == b'\x0C':
						result = 1000.0
					elif edt == b'\x0D':
						result = 10000.0
					else:
						result = 0.0
					
				elif epc == 'amount_energy_normal':
					result = int.from_bytes(edt, 'big')
					result *= sem_info['epc_coefficient'] * sem_info['unit_amount_energy']
					
				elif epc == 'recent_amount_energy_norm':
					dt = sem.parse_datetime(edt[0:7])
					energy = int.from_bytes(edt[7:11], 'big')
					energy *= sem_info['epc_coefficient'] * sem_info['unit_amount_energy']
					result = [dt, energy]
				
				elif epc == 'hist_amount_energy1_norm':
					result = binascii.b2a_hex(edt)
					
				sem_info[epc] = result
				if LCD_LOG == False:
					sys.stdout.write('[Get]: {}, {}\n'.format(epc, result))

			else:  # Get失敗x10
				sys.stderr.write('[Error]: Can not get {}.\n'.format(epc))
				sem_exist = False
				break
		
	if sem_exist:
		time.sleep(3)
		start = time.time()
		LCD_DT = True
		while True:
			try:
				if (time.time() - pana_ts > 0):	  # 12時間毎にPANA認証を更新
					sys.stdout.write('PANA re-connection...\n')
					sem_exist = y3.restart_pac()
					if sem_exist:
						pana_ts = time.time() + PAC_LIFETIME	# 次回の認証時刻を保存(12時間後)
						sys.stdout.write('Requested PANA re-connection done.\n')
					else:
						pana_ts = time.time() + 60				# 60秒後に再認証
						sys.stdout.write('Fail to connect.\n')
					'''
						sem_exist = False
						pana_done = False
						st = time.time()
						while True:
							if sem_inf_list:
								pana_ts = time.time() + PAC_LIFETIME	# 次回の認証時刻を保存(12時間後)
								sys.stdout.write('Successfully done.\n')			   
								time.sleep(3)
								pana_done = True
								break
							elif time.time() - st > 20: 	# PANA認証失敗によるタイムアウト
								pana_done = False
								pana_ts = time.time() + 60				# 60秒後に再認証
								sys.stdout.write('Fail to connect.\n')
								break
							else:
								time.sleep(0.1) 					   
					
					if not pana_done:
						break		# PANA認証失敗でbreakする
					'''
				sem_get('instant_power')	# Get
				
				while True: 	# GetRes待ちループ		  
					rcd_time = time.time()		# rcd_time[s]
					new_dt = datetime.datetime.fromtimestamp(rcd_time)
					
					# ログファイルメンテナンス
					pow_logfile_maintainance(saved_dt, new_dt)
					saved_dt = new_dt
					
					if y3.get_queue_size():
						msg_list = y3.dequeue_message()
						if msg_list['COMMAND'] == 'ERXUDP':
							led.oneshot()
							parsed_data = sem.parse_frame(msg_list['DATA'])
							
							if parsed_data:
								if parsed_data['tid'] != tid_counter:
									errmsg = '[Error]: ECHONET Lite TID mismatch\n'
									sys.stderr.write(errmsg)
									
								else:
									watt_int = int.from_bytes(parsed_data['ptys'][0]['edt'], 'big', signed=True)
									t = datetime.datetime.today()
									if LCD_LOG:
									#	sys.stdout.write('SmartMTR')
										if LCD_DT == True:
											LCD_DT = False
											t_str = t.strftime('%y/%m/%d')
										else:
											LCD_DT = True
											t_str = t.strftime('%H:%M:%S')
										sys.stdout.write(t_str)
										sys.stdout.write('{:4d} W\n'.format(watt_int))
									else:
										sys.stdout.write('[{:5d}] {:4d} W\n'.format(tid_counter, watt_int))
							
									try:	# 一時ログファイルに書き込み
										f = open(TMP_LOG_FILE, 'a') 	   # rcd_time[ms] (JavaScript用)
										f.write('{},{}\n'.format(round(rcd_time), watt_int))
										f.close()
									except:
										sys.stderr.write('[Error]: can not write to file.\n')
							
									if sock:  # UNIXドメインソケットで送信
										sock_data = json.dumps({'time': rcd_time, 'power': watt_int}).encode('utf-8')
										try:
											sock.send(sock_data)
										except:
											sys.stderr.write('[Error]: Broken socket.\n')

									if sock_udp: # UDPでテキスト送信
										msg = ('{} {}\n'.format(DEVICE,watt_int)).encode('utf-8')
										try:
											sock_udp.sendto(msg, (user_conf.SOCK_UDP, user_conf.SOCK_PORT))
										except:
											sys.stderr.write('[Error]: Broken UDP socket.\n')
							
									break
							
							else:	# 電文が壊れている
								errmsg = '[Error]: ECHONET Lite frame error\n'
								sys.stderr.write(errmsg)
							
						elif msg_list['COMMAND'] == 'EVENT C0':
							if LCD_LOG == False:
								sys.stdout.write('[PS]: wake up\n')
						
						else:	# 電文が壊れている???
							errmsg = '[Error]: Unknown data received. '
							sys.stderr.write(errmsg)
							sys.stderr.write('(' + msg_list['COMMAND'] + ')\n')
						
					else:	# GetRes待ち
						while sem_inf_list:
							inf = sem_inf_list.pop(0)
							if LCD_LOG == False:
								sys.stdout.write('[Inf]: {}\n'.format(inf['DATA']))
						
						if time.time() - start > 20:	# GetRes最大待ち時間: 20s
							sys.stderr.write('[Error]: Time out. @loop\n')
							
							try:	# 一時ログファイルに書き込み
								f = open(TMP_LOG_FILE, 'a')
								f.write('{},None\n'.format(round(rcd_time)))
								f.close()
							except:
								sys.stderr.write('[Error]: can not write to file.\n')
							break
							
						time.sleep(0.1)
				
			except KeyboardInterrupt:
				break

			if LCD_LOG == False:
				sys.stdout.write('[PS]: Go to sleep\n')
			sys.stdout.flush()
			sys.stderr.flush()
			if user_conf.SEM_INTERVAL > 0:
				y3.set_sleep_mode()
				while True:
					if (time.time() - start) >= user_conf.SEM_INTERVAL:
						start = time.time()
						y3wakeup()
						break
					else:
						time.sleep(1)
			else:
				time.sleep(1)
	else:
		sys.stderr.write('[Error]: Can not connect with a smart energy meter.\n')

	# 終了処理
	if sock:
		try:
			sock.close()
		except:
			sys.stderr.write('[Error]: Broken socket.\n')

	if LCD_LOG:
		sys.stdout.write('Wi-SUN  RESET\n')
	else:
		sys.stdout.write('\nWi-SUN reset...\n')
	y3reset()
	y3.terminate()
	y3.uart_close()
	led.terminate()
	gpio.cleanup()
	
	if os.path.exists(TMP_LOG_FILE):
		os.remove(TMP_LOG_FILE)

	if LCD_LOG:
		sys.stdout.write('[EOF]\n\n')
	else:
		sys.stdout.write('Bye.\n')
	sys.exit(0)
