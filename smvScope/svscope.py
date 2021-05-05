#!/usr/bin/env python3

import os,sys
import ctypes
import time
from smvScope import lib61850
import json
from datetime import datetime

from flask import Flask, Response, render_template

application = Flask(__name__)

colors = ['rgb(99, 132, 255)','rgb(255, 99, 132)','rgb(132, 255, 99)','rgb(99, 99, 99)','rgb(0, 132, 255)','rgb(255, 0, 132)','rgb(132, 255, 0)','rgb(99, 99, 0)']

dataConfig = {
                'labels': [],
                'datasets': [],
            }

optionsConfig = {
                'animation': False,
                'responsive': True, #for resizing
                'title': {
                    'display': True,
                    'text': 'SMV 9-2 values',
                },
                'tooltips': {
                    'mode': 'index',
                    'intersect': False,
                },
                'hover': {
                    'mode': 'nearest',
                    'intersect': True,
                },
                'scales': {
                    'x': {
                        'title': { 
                            'display': True,
                            'text': 'smpCnt',
                        },
                        #//type: 'linear',#//linear causes first and last sample to connect, causing a line
			'beginAtZero': True,
                        #//min: 0, //seems to start at 1
                        'max': 4000,
                        'minRotation': 0,
                        'maxRotation': 0,
                    },
                    'y': {
                        'title': { 
                            'display': True,
                            'text': 'value',
                        },
                        'type': 'linear',
                        'minRotation': 0,
                        'maxRotation': 0,
                    },
                }
            }


oldSmpCnt = 0
smp = {}
smp[0] = []
seconds = 0
running = False
dataSets = 0


def SetDataConfig(amount):
    dataConfig['datasets'] = []
    for idx in range(amount):
        channel = f"Channel {idx}" 
        dataConfig['datasets'].append( {
                    'pointRadius': 0,
                    'stepped': False,
                    'tension': 0,
                    'label': channel,
                    'backgroundColor': colors[idx],
                    'borderColor': colors[idx],
                    'data': [],
                    'fill': False,
                    'parsing': False,
                    'normalized': True,
                    'borderDash': [],
                } )


def svUpdateListener ( subscriber, parameter,  asdu):
    global oldSmpCnt
    global smp
    global seconds
    global running
    global dataSets

    #svID = lib61850.SVSubscriber_ASDU_getSvId(asdu)
    #if svID != None:
    #    print("  svID=(%s)" % svID)

    smpCnt = lib61850.SVSubscriber_ASDU_getSmpCnt(asdu)


    size = lib61850.SVSubscriber_ASDU_getDataSize(asdu)

    if smpCnt != (oldSmpCnt + 1) % 4000 and running:
        #print("ERROR: smpCnt expected: %i, received: %i" % ((oldSmpCnt + 1) % 4000, smpCnt))
        # fill missing packets with null samples
        c = smpCnt
        o = oldSmpCnt + 1
        while c != o:
            indices = []
            for _ in range(0,size,8):
                indices.append( {'y': 0 } )
            smp[seconds].append( {'x': smpCnt, 'index': indices } )
            o = (o + 1) % 4000

    #print("  smpCnt: %i" % smpCnt)
    #print("  confRev: %u" % lib61850.SVSubscriber_ASDU_getConfRev(asdu))
    #print("  smpSynch: %u" % lib61850.SVSubscriber_ASDU_getSmpSynch(asdu))

    indices = []
    #print("  size:%i" % size)
    for item in range(0,size,8):
        indices.append( {'y': lib61850.SVSubscriber_ASDU_getINT32(asdu, item) } )

    smp[seconds].append( {'x': smpCnt, 'index': indices } )

    if oldSmpCnt > smpCnt: # trigger second increment when the counter loops.
        seconds = seconds + 1
        smp[seconds] = []
        dataSets = int(size/8)

    oldSmpCnt = smpCnt
    running = True


def smv_data():
    while True:
        if seconds > 2:
            allData = {}
            if True:
                allData['dataSets'] = smp[seconds-1]
            if True:
                SetDataConfig(dataSets)
                allData['config_data'] = dataConfig
                allData['config_options'] = optionsConfig
            json_data = json.dumps(allData)
            #json_data = json.dumps({ 'dataSets': smp[seconds-1] })
            yield f"data:{json_data}\n\n"
        time.sleep(1)


@application.route('/')
def index():
    return render_template('index.html')


@application.route('/chart-data')
def chart_data():
    return Response(smv_data(), mimetype='text/event-stream')


def determine_path():
    """Borrowed from wxglade.py"""
    try:
        root = __file__
        if os.path.islink (root):
            root = os.path.realpath (root)
        return os.path.dirname (os.path.abspath (root))
    except:
        print("I'm sorry, but something is wrong.")
        print("There is no __file__ variable. Please contact the author.")
        sys.exit ()
        
def start ():
    path = determine_path()
    print( "path:" + path )
    print("Data files path:")

    files = [f for f in os.listdir(path + "/templates")]
    print("\n" + path + "/templates")
    print(files)

    print("\n" + path + "/static")
    files = [f for f in os.listdir(path + "/static")]
    print(files)
    print("\n")
    
    receiver = lib61850.SVReceiver_create()
    lib61850.SVReceiver_setInterfaceId(receiver, sys.argv[1])

    subscriber = lib61850.SVSubscriber_create(None, 0x4000)

    cb = lib61850.SVUpdateListener(svUpdateListener)

    lib61850.SVSubscriber_setListener(subscriber, cb, None)
    lib61850.SVReceiver_addSubscriber(receiver, subscriber)

    lib61850.SVReceiver_start(receiver)

    if lib61850.SVReceiver_isRunning(receiver) == False:
        print("Failed to start SV subscriber. Reason can be that the Ethernet interface doesn't exist or root permission are required.")
        sys.exit(-1)

    application.run(debug=False, threaded=True) # debug=true will start 2 subscriber threads

    lib61850.SVReceiver_stop(receiver)
    lib61850.SVReceiver_destroy(receiver)

if __name__ == "__main__":
    start()




