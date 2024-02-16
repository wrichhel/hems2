#! /usr/bin/python
import gpiozero as GPIO
from gpiozero import MCP3008
import logging
import socket
import os
from datetime import datetime
from datetime import timedelta
import configparser
from time import sleep
import csv
import signal

"""
1) Initialize software
2) Initialize data collection hardware
3) Initialize data storage
4) Initialize connection to data archival host
5) Data loop
5.1)	Set up keyboard interrupt trap
5.2)	For each connected sensor
5.2.1)		Initiate reading
5.2.2)		Retrieve reading into buffer
5.3)	Write buffer to local storage
5.4)	Write buffer to network storage
5.5)	compute pause to next reading
5.6)	Sleep until time for next reading
6)	Handle KeyboardInterrupt
6.1)		Close data file cleanly
6.2		Log completion
7) Exit
"""

class Tag():
	chnl = -1
	loc = ''
	def __init__(self, rdgChannel: int, rdgLocation: str):
		self.chnl = rdgChannel
		self.loc = rdgLocation
		print(f'Channel {self.chnl}, location {self.loc}')

	def __str__(self):
		return f'Channel {self.chnl} is placed at: {self.loc}'

class TempTag(Tag):
	def __init__ (self, rdgChannel: int, rdgLocation: str, units: str):
		super().__init__(rdgChannel, rdgLocation)
		self.units = units

	def ScaledReading(self):
		rawReading = float(MCP3008(channel = self.chnl).value)
		scaledReading = 100.*(rawReading * 3.3 - .5)
		if(self.units == 'F'):
			scaledReading = CtoF(scaledReading)
		return round(scaledReading,2)


def ReadConfigs(filename):
	config = configparser.ConfigParser()
	config.read_file(open(filename))
	return config

def ParseConfigs(config):
	try:
		configDict = {
			'logInterval' : int(config['DEFAULT']['LOG_INTERVAL']),
			'dataDir' : config['DEFAULT']['DATA_DIR'],
			'dataFileName' : config['DEFAULT']['DATA_FILENAME'],
			'logFileName' : config['DEFAULT']['LOG_FILENAME'],
			'sensorCount' : int(config['DEFAULT']['SENSOR_COUNT']),
			'logLevel': int(config['DEFAULT']['LOGLEVEL']),
			'units': config['DEFAULT']['UNITS'],
		}
	except KeyError as x:
		print (list(config['DEFAULT'].keys()))
		exit (1)
	dataPoints = list()
	for channel in range(configDict['sensorCount']):
		section = 'SENSOR'+str(channel)
		newPoint = TempTag(int(config[section]['CHANNEL']), config[section]['LOCATION'], config[section]['UNITS'])
		dataPoints.append(newPoint)
	print(configDict, dataPoints)
	return configDict, dataPoints


def InitializeSW():
	config = ReadConfigs('hems.ini')
	configDict, rdgs = ParseConfigs(config)
	logger = InitializeHemsLog(configDict)
	return logger, configDict, rdgs

def InitializeHW(rdgsList, logger):
	pass

def InitializeHemsLog(configDict):
	logFileName = configDict['dataDir'] + '/' + configDict['logFileName']
	print (logFileName)
	logging.basicConfig(format = "%(asctime)s %(levelname)s: %(message)s", 
		filename = logFileName, 
		filemode="a")
	logger = logging.getLogger()
	logger.setLevel(configDict['logLevel'])
	print (logger)
	return logger

def CtoF(temp:float):
	return(9. * temp/5.) + 32.


def CalcPause(lastReadingTime, interval):
	cT = lastReadingTime
	roundedTime = datetime(cT.year,cT.month,cT.day,cT.hour,cT.minute,cT.second)
	thePauseTime = roundedTime - cT + timedelta(seconds = interval)
	thePause = float(thePauseTime.seconds+ thePauseTime.microseconds/1000000)
	return thePause

def SetFileName(dir,baseName):
	fileName = dir+'/'+datetime.now().strftime('%Y%m%d')+baseName
	print(fileName)
	return fileName

def WriteReadings(scanTime, rdgList, reading,fileName):
	newFile = not (os.path.exists(fileName))
	fieldNames = [
		"ScanTime"
	]
	for chn in range(len(rdgList)):
		fieldNames.append("chn_"+str(rdgList[chn].chnl))
	logger.debug(fieldNames)

	writeDict = {
	"ScanTime" : scanTime.strftime('%Y-%m-%d %H:%M:%S')
	}
	for chn in range(len(rdgList)):
		writeDict["chn_"+str(rdgList[chn].chnl)] = reading[chn]
	logger.debug(writeDict)
	with open(fileName, "a", newline ="") as csvfile:
		csvfile= open(fileName, "a", newline = "")
		writer = csv.DictWriter(csvfile, fieldnames= fieldNames)
		if newFile:
			writer.writeheader()
			newFile = False
			logger.info(f"New file opened: {fileName}")
		writer.writerow(writeDict)
	return csvfile

def DataLoop(rdgList, configDict):
	logger.info('Entering DataLoop')
	print(f'HEMS recording temperature data. Press <Control-C> to terminate')
	readings = 0
	try:
		while True:
			readingTime = datetime.now()
			dataFile = SetFileName(configDict['dataDir'],configDict["dataFileName"])
			currentReadings = list()
			scanInt = configDict["logInterval"]
			for chn in range(configDict["sensorCount"]):
				currentReadings.append(rdgList[chn].ScaledReading())
			f = WriteReadings(readingTime, rdgList, currentReadings, dataFile)
			readings += 1
			f.close()
			thePause = CalcPause(readingTime,scanInt)
			logger.debug(f'{readings}: {readingTime},{round(thePause,3)}')
			sleep(thePause)
	except KeyboardInterrupt:
		f.close()
		logger.info(f'Data logging interrupted by ctl-c after {readings} scans')

logger, configDict, rdgs = InitializeSW()
logger.info('Starting HEMS - logging temperature data')
logger.info(f'{configDict["sensorCount"]} sensors being monitored:')
for i in range (len(rdgs)):
	logger.info(f'channel {rdgs[i].chnl} at {rdgs[i].loc}')
InitializeHW(rdgs, logger)
logger.info(configDict)
DataLoop(rdgs, configDict)