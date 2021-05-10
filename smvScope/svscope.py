#!/usr/bin/env python3

import os,sys
import ctypes
import time
from smvScope import lib61850
import json
from datetime import datetime
import types

from flask import Flask, Response, render_template, request

application = Flask(__name__)

colors = ['rgb(99, 132, 255)','rgb(255, 99, 132)','rgb(132, 255, 99)','rgb(99, 99, 99)','rgb(0, 132, 255)','rgb(255, 0, 132)','rgb(132, 255, 0)','rgb(99, 99, 0)']

dataConfig = {
                'labels': [],
                'datasets': [],
            }

optionsConfig = {
                'animation': False,
                'responsive': False, #for resizing
                'height': 30,
                'maintainAspectRatio': False,
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
streamFilter = None
streamList = {}
streamInfo = {}
gaps = 0

control_data_d = {}
control_data_d_update = True
# select stream: streamSelect
control_data_d['streamSelect_items'] = [] # list of streams
control_data_d['streamSelect'] = { "streamValue": 0 } # selected stream

# stream info
#control_data_d['smvSelectedStream'] = { 'appid' : 0x4000 , 'svID' : 'one', 'DataSet' : 'smp1', 'samplesReceived' : 0 }

# select data: R_Amp S_Amp T_Amp N_Amp, R_Volt S_Volt T_Volt N_Volt
control_data_d['dataSelect'] = { "R_Amp": True, "S_Amp":True, "T_Amp": True, "N_Amp": True, "R_Volt": True, "S_Volt": True, "T_Volt": True, "N_Volt": True }

# filter streams control
#control_data_d['smvFilter'] = { 'appid' : 0x4000 , 'svID' : 'one', 'DataSet' : 'smp1' } # current filter settings
#control_data_d['smvFilterEnabled'] = { 'appid' : True , 'svID' : False, 'DataSet' : False } # current filter control settings

# time control: rangeValue offsetValue
control_data_d['smvTime'] = { 'rangeValue' : 4000, 'offsetValue' : 0 } # current timescale settings

# trigger control: triggerCheck channelSelect compareSelect tresholdInput
control_data_d['smvTrigger'] = { 'triggerCheck' : False, 'channelSelect' : 0, 'compareSelect' : 1, 'tresholdInput' : 0 } # current filter settings

# sample info
#control_data_d['smvSample'] = { 'index' : 0, 'sample' : 'data' } # all data from a specific sample

# error messages; missing samples, packets, lost streams etc.
#control_data_d['errors'] = { 'message' : 'text' } # messages related to errors

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


# 
# critical path
# 
def svUpdateListener ( subscriber, parameter,  asdu):
    global oldSmpCnt
    global smp
    global seconds
    global running
    global dataSets
    global streamFilter
    global streamList
    global streamInfo
    global gaps

    svID = str(lib61850.SVSubscriber_ASDU_getSvId(asdu))
    streamList[svID] = time.monotonic() # store time of last received sample (this also serves a a way to know the streams that are received)

    if streamFilter != None and svID != streamFilter:
        print("DEBUG: filter not matched for svID: " + svID)
        return

    smpCnt = lib61850.SVSubscriber_ASDU_getSmpCnt(asdu)
    #print("  smpCnt: %i" % smpCnt)

    #print("  confRev: %u" % lib61850.SVSubscriber_ASDU_getConfRev(asdu))
    #print("  smpSynch: %u" % lib61850.SVSubscriber_ASDU_getSmpSynch(asdu))
    size = lib61850.SVSubscriber_ASDU_getDataSize(asdu)
    #print("  size:%i" % size)

    # check for missing packets. first packet is ginored
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
            gaps = gaps + 1 # counter
            o = (o + 1) % 4000

    # list with all y values (4x amp and 4x volt for 9-2 LE)
    indices = []
    for item in range(0,size,8):
        indices.append( {'y': lib61850.SVSubscriber_ASDU_getINT32(asdu, item) } )

    # json list with { x: samplecount, index: [{y:_},{y:_},{y:_},...] }
    smp[seconds].append( {'x': smpCnt, 'index': indices } )

    # increment the secod counter each 4000 sampled, i.e each second
    if oldSmpCnt > smpCnt: # trigger second increment when the counter loops.(i.e. when the previous smpCnt is higher then the current, we assume we looped around from 4000 to 0)
        seconds = seconds + 1
        smp[seconds] = [] # create a new list to store the samples
        dataSets = int(size/8)
        streamInfo = {
                             'size': size, 
                             'seconds': seconds, 
                             'svID': svID,
                             'confRev': lib61850.SVSubscriber_ASDU_getConfRev(asdu), 
                             'smpSync': lib61850.SVSubscriber_ASDU_getSmpSynch(asdu),
                             'gaps': gaps,
                           }
        # OPTIONAL; not in 9-2 LE, source:https://knowledge.rtds.com/hc/en-us/article_attachments/360074685173/C_Kriger_Adewole_RTDS.pdf
        if lib61850.SVSubscriber_ASDU_hasDatSet(asdu) == True:
            streamInfo['datset'] = lib61850.SVSubscriber_ASDU_getDatSet(asdu)
        if lib61850.SVSubscriber_ASDU_hasSmpRate(asdu) == True:
            streamInfo['smpRate'] = lib61850.SVSubscriber_ASDU_getSmpRate(asdu)
        if lib61850.SVSubscriber_ASDU_hasRefrTm(asdu) == True:
            streamInfo['RefTm'] = lib61850.SVSubscriber_ASDU_getRefrTmAsMs(asdu)
        if lib61850.SVSubscriber_ASDU_hasSmpMod(asdu) == True:
            streamInfo['smpMod'] = lib61850.SVSubscriber_ASDU_getSmpMod(asdu)
                             

    oldSmpCnt = smpCnt
    running = True # to ignore the first sample, so that oldSmpCnt is initialized


def smv_data():
    global smp
    global streamInfo
    config_set = False
    while True:
        if seconds > 2:
            allData = {}

            if config_set == False:
                SetDataConfig(dataSets)
                allData['config_data'] = dataConfig
                allData['config_options'] = optionsConfig
                config_set = True

            allData['dataSets'] = smp[seconds-1]
            allData['stream_info'] = streamInfo

            json_data = json.dumps(allData)
            #json_data = json.dumps({ 'dataSets': smp[seconds-1] })
            yield f"data:{json_data}\n\n"
        time.sleep(1)


def update_setting(control, value):
    global control_data_d

    if control == "streamValue":
        global streamFilter
        global oldSmpCnt
        global smp
        global seconds
        global running
        global dataSets
        global streamInfo
        global gaps
        # if filter becomes a different value
        if streamFilter != control_data_d['streamSelect_items'][int(value)]:
            streamFilter = control_data_d['streamSelect_items'][int(value)]
            # reset values after filter change
            oldSmpCnt = 0
            smp = {}
            smp[0] = []
            seconds = 0
            running = False
            dataSets = 0
            streamInfo = {}
            gaps = 0
            print("INFO: streamfilter set to: " + streamFilter)
        return True
    if control == "R_Amp": # handled by client
        return True
    if control == "S_Amp": # handled by client
        return True
    if control == "T_Amp": # handled by client
        return True
    if control == "N_Amp": # handled by client
        return True
    if control == "R_Volt": # handled by client
        return True
    if control == "S_Volt": # handled by client
        return True
    if control == "T_Volt": # handled by client
        return True
    if control == "N_Volt": # handled by client
        return True
    if control == "rangeValue": # handled by client
        if value > 4000 or value < 0:
            return False
        return True
    if control == "offsetValue": # handled by client
        if value > 4000 or value < 0:
            return False
        return True
    if control == "triggerCheck": # handled by client
        return True
    if control == "channelSelect": # handled by client
        return True
    if control == "compareSelect": # handled by client
        return True
    if control == "tresholdInput": # handled by client
        return True
    return False

@application.route('/')
def index():
    return render_template('index.html')


@application.route('/chart-data')
def chart_data():
    return Response(smv_data(), mimetype='text/event-stream')


def control_data_g():
    global control_data_d
    global control_data_d_update
    global streamFilter
    global streamList
    streamList_Length = 0
    while True:
        time.sleep(0.1) # check for changes every 0.1 seconds, and if so send update to client

        # update the stream list, if a new entry is found
        if len(streamList) > streamList_Length:
            control_data_d['streamSelect_items'] = []
            for stream in streamList:
                control_data_d['streamSelect_items'].append(stream)
            streamList_Length = len(streamList)
            if streamFilter == None:
                streamFilter = control_data_d['streamSelect_items'][0]
            control_data_d_update = True

        # update the controls when a control is updated
        if control_data_d_update == True:
            control_data_d_update = False
            json_data = json.dumps(control_data_d)
            yield f"data:{json_data}\n\n"



@application.route('/control-data')
def control_data():
    return Response(control_data_g(), mimetype='text/event-stream')


@application.route('/control-setting', methods=['POST'])
def control_setting(): # post requests with data from client-side javascript events
    global control_data_d
    global control_data_d_update
    content = request.get_json(silent=True)
    for subject in control_data_d:
        if isinstance(control_data_d[subject], dict):    
            for item in control_data_d[subject]:
                if item == content['id']:
                    if update_setting(content['id'],content['value']) == True: # update the setting in the app
                        control_data_d[subject][item] = content['value'] # update the control in the client if succesfull
                        control_data_d_update = True
                    else:
                        print("ERROR: could not update setting: " + content['id'])

    return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


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

    application.run(host="0.0.0.0", debug=False, threaded=True) # debug=true will start 2 subscriber threads

    lib61850.SVReceiver_stop(receiver)
    lib61850.SVReceiver_destroy(receiver)

if __name__ == "__main__":
    start()




