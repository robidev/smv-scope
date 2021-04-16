#!/usr/bin/env python3

import os,sys
import ctypes
import time
import lib61850
import json
from datetime import datetime

from flask import Flask, Response, render_template

application = Flask(__name__)


oldSmpCnt = 0
smp = {}
smp[0] = []
seconds = 0
running = False

def svUpdateListener ( subscriber, parameter,  asdu):
    global oldSmpCnt
    global smp
    global seconds
    global running

    #svID = lib61850.SVSubscriber_ASDU_getSvId(asdu)
    #if svID != None:
    #    print("  svID=(%s)" % svID)

    smpCnt = lib61850.SVSubscriber_ASDU_getSmpCnt(asdu)

    if smpCnt != (oldSmpCnt + 1) % 4000 and running:
        #print("ERROR: smpCnt expected: %i, received: %i" % ((oldSmpCnt + 1) % 4000, smpCnt))
        # fill missing packets with null samples
        c = smpCnt
        o = oldSmpCnt + 1
        while c != o:
            smp[seconds].append( {'x': o, 
                'R': 0, 
                'S': 0, 
                'T': 0,
                'N': 0 }
                )
            o = (o + 1) % 4000

    #print("  smpCnt: %i" % smpCnt)
    #print("  confRev: %u" % lib61850.SVSubscriber_ASDU_getConfRev(asdu))
    #print("  smpSynch: %u" % lib61850.SVSubscriber_ASDU_getSmpSynch(asdu))
    #size = lib61850.SVSubscriber_ASDU_getDataSize(asdu)
    #print("  size:%i" % size)
    #for item in range(0,size,8):
    #    print("   DATA    [%i]: %i" % (item,lib61850.SVSubscriber_ASDU_getINT32(asdu, item)))
    #    print("   QUALITY [%i]: %i" % (item,lib61850.SVSubscriber_ASDU_getINT32(asdu, item+4)))

    smp[seconds].append( {'x': smpCnt, 
        'R': lib61850.SVSubscriber_ASDU_getINT32(asdu, 0), 
        'S': lib61850.SVSubscriber_ASDU_getINT32(asdu, 8), 
        'T': lib61850.SVSubscriber_ASDU_getINT32(asdu, 16),
        'N': lib61850.SVSubscriber_ASDU_getINT32(asdu, 24)}
        )

    if oldSmpCnt > smpCnt: # trigger second increment when the counter loops.
        seconds = seconds + 1
        smp[seconds] = []

    oldSmpCnt = smpCnt
    running = True



@application.route('/')
def index():
    return render_template('index.html')


@application.route('/chart-data')
def chart_data():
    def smv_data():
        while True:
            if seconds > 2:
                json_data = json.dumps(smp[seconds-1])
                yield f"data:{json_data}\n\n"
            time.sleep(1)

    return Response(smv_data(), mimetype='text/event-stream')



receiver = lib61850.SVReceiver_create()
lib61850.SVReceiver_setInterfaceId(receiver, sys.argv[1])

subscriber = lib61850.SVSubscriber_create(None, 0x4000)

cb = lib61850.SVUpdateListener(svUpdateListener)

lib61850.SVSubscriber_setListener(subscriber, cb, None)
lib61850.SVReceiver_addSubscriber(receiver, subscriber)

lib61850.SVReceiver_start(receiver)

if lib61850.SVReceiver_isRunning(receiver) == False:
    print("Failed to start SV subscriber. Reason can be that the Ethernet interface doesn't exist or root permission are required.")
    exit(-1)


if __name__ == '__main__':
    application.run(debug=False, threaded=True) # debug=true will start 2 subscriber threads


lib61850.SVReceiver_stop(receiver)
lib61850.SVReceiver_destroy(receiver)







