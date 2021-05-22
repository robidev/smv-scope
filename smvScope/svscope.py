#!/usr/bin/env python3

import os,sys
import ctypes
import time
from smvScope import lib61850
import json
from datetime import datetime
import types

from flask import Flask, Response, render_template, request

import socket
from struct import *
import threading
import binascii

application = Flask(__name__)


control_data_d = {}
control_data_d_update = True

# streamlistener data
streamListingThread = threading.Thread()
streamList = []
StreamDetails = {}

#stream data
subscribers_list = []
# subscribe/unsibscribe data
receiver = None
subscribers = {}
streamFilter = {}

# subscriber callback data
smv_data = {}
sec_counter = {}
streamInfo = {}
oldSmpCnt = {}

log_list = []

# listbox data
control_data_d['streamSelect_items'] = [] # list of streams
control_data_d['streamSelect'] = { "streamValue": [] } # selected stream



# duration can be > 0 to set a timeout, 0 for immediate and -1 for infinite
def getSMVStreams(interface, duration):
    global streamList
    global StreamDetails
    #Convert a string of 6 characters of ethernet address into a dash separated hex string
    def eth_addr (a) :
        b = "%.2x:%.2x:%.2x:%.2x:%.2x:%.2x" % ((a[0]) , (a[1]) , (a[2]), (a[3]), (a[4]) , (a[5]))
        return b

    ret =  os.system("ifconfig %s promisc" % interface)
    if ret != 0:
        print_to_log("error setting promiscuous mode on %s" % sys.argv[1])
        sys.exit(-1)

    #create an INET, raw socket
    #define ETH_P_ALL    0x0003          /* Every packet (be careful!!!) */
    # SMV                0x88ba
    # GOOSE              0x88b8
    s = socket.socket( socket.AF_PACKET , socket.SOCK_RAW , socket.ntohs(0x88ba))
    #s.setsockopt(socket.SOL_SOCKET, 25, str(interface + '\0').encode('utf-8'))
    s.bind((interface,0))

    streams = []

    # handle duration
    if duration == 0:
        s.settimeout(0)
        s.setblocking(0)
    if duration > 0:
        s.settimeout(1)
        deadline = time.perf_counter() + duration

    while True:
        time.sleep(5.0) # TODO make this more configurable
        if duration > 0 and time.perf_counter() > deadline:
            break
        try:
            packet = s.recvfrom(65565)
        except:
            continue

        #packet string from tuple
        packet = packet[0]
        #parse ethernet header
        eth_length = 14
        dst = eth_addr(packet[0:6])
        src = eth_addr(packet[6:12])
        # parse GOOSE streams, and make a list of them (record appid, MAC, gocbRef, )
        # when an element is chosen, the subscriber can be initialised
        # when a different element is chosen, re-init subscriber with new gocbRef    
        appid = unpack('!H' , packet[eth_length:eth_length+2] )[0]

        svID_length = 31
        svID_size = int(packet[svID_length + 1])
        svID = packet[svID_length + 2 : svID_length + 2 + svID_size].decode("utf-8")
        #print_to_log("mac: %s, appid: %i, gocbRef: %s, gocbRef_size: %i" % (dst, appid, gocbRef, gocbRef_size))
        #item = "%s %i %s" % (dst,appid,gocbRef)
        if svID not in StreamDetails:
            StreamDetails[svID] = {'src': src, 'dst': dst, 'appid': appid}
        else:
            if StreamDetails[svID]['src'] != src or StreamDetails[svID]['dst'] != dst:
                print_to_log("ERROR: goose collision! message received with matching gocbref: %s but;" % svID)
                if StreamDetails[svID]['src'] != src:
                    print_to_log("  src mac not matching: expected: %s, received: %s" % (StreamDetails[svID]['src'], src))
                if StreamDetails[svID]['dst'] != dst:
                    print_to_log("  dst mac not matching: expected: %s, received: %s" % (StreamDetails[svID]['dst'], dst))               
                if StreamDetails[svID]['appid'] != appid:
                    print_to_log("  appid not matching: expected: %s, received: %s" % (StreamDetails[svID]['appid'], appid))
                print_to_log("NOTE: gocbref are expected to be unique for each stream")

        for channel in range(8):# TODO: base range on decoded size
            item = "%s,%i" % (svID,channel)
            if item not in streams:
                streams.append(item)

        if duration == 0:
            break
        if duration < 0:
            streamList = streams

    s.close()
    return streams


@application.route('/')
def index():
    control_data_d_update = True
    return render_template('index.html')


def update_setting(subject, control, value):
    if control == "streamValue":
        global control_data_d
        global control_data_d_update
        global streamList
        global subscribers_list
        global receiver
        global smv_data

        dif_off = set(subscribers_list) - set(value)
        dif_on = set(value) - set(subscribers_list)
        #print_to_log(dif_off)
        #print_to_log(dif_on)
        for item in dif_off:
            stream = streamList[int(item)-1].split(',') # svID from itemlist
            svID = stream[0]
            channel = int(stream[1])
            unsubscribe(receiver, svID, channel, start = True)
            print_to_log("INFO: SMV item %s unsubscribed" % item)
        for item in dif_on:
            stream = streamList[int(item)-1].split(',') # svID from itemlist
            svID = stream[0]
            channel = int(stream[1])

            if svID not in smv_data:
                sec_counter[svID] = 0
                smv_data[svID] = {} # ensure we initialised the dataset
                smv_data[svID][0] = []
                oldSmpCnt[svID] = 0
            subscribe(receiver, svID, channel, start = True)
        # differences have been processed, value is the actual state
        subscribers_list = value

        if lib61850.SVReceiver_isRunning(receiver) == False:
            print_to_log("ERROR: Failed to enable SMV subscriber")
        else:# set control-data in the client control if succesfull
            control_data_d[subject][control] = value 
        # update the control now
        control_data_d_update = True
        return True
    return False


@application.route('/control-setting', methods=['POST'])
def control_setting(): # post requests with data from client-side javascript events
    global control_data_d
    content = request.get_json(silent=True)
    for subject in control_data_d:
        if isinstance(control_data_d[subject], dict):    
            for item in control_data_d[subject]:
                if item == content['id']:
                    if update_setting(subject, content['id'],content['value']) != True: # update the setting
                        print_to_log("ERROR: could not update setting: " + content['id'])
    return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


def control_data_g():
    global control_data_d
    global control_data_d_update
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
            control_data_d_update = True

        # update the controls when a control is updated
        if control_data_d_update == True:
            control_data_d_update = False
            json_data = json.dumps(control_data_d)
            yield f"data:{json_data}\n\n"


@application.route('/control-data')
def control_data():
    return Response(control_data_g(), mimetype='text/event-stream')


def stream_data_g():
    global smv_data
    global streamInfo
    global sec_counter
    global streamFilter

    second_update = 0
    while True:
        allData = {}
        allData['dataSets'] = {}
        allData['stream_info'] = {}
        new_data = False

        index = 0
        for svID in streamFilter:
            second = sec_counter[svID] - 1
            if second < 1: #ignore the first 2 seconds, so items can be initialised
                continue
            if index == 0 and second > second_update: # check for the first active item if second was incremented
                second_update = second # reset it until next increment
                new_data = True # record data from all datasets

            #if we have new data
            if new_data == True:
                allData['dataSets'][svID] = smv_data[svID][second]
                allData['stream_info'][svID] = streamInfo[svID]
            index = index + 1

        if new_data == True:
            json_data = json.dumps(allData)
            yield f"data:{json_data}\n\n"
            new_data = False
        time.sleep(0.1) 

@application.route('/stream-data')
def stream_data():
    return Response(stream_data_g(), mimetype='text/event-stream')

def print_to_log(message):
    global log_list
    log_list.append(message)

def log_data_g():
    global log_list
    log_length = 0
    while True:
        if len(log_list) > log_length:
            json_data = json.dumps(log_list[log_length : ])
            log_length = len(log_list)
            yield f"data:{json_data}\n\n"
        time.sleep(0.3)

@application.route('/log-data')
def log_data():
    return Response(log_data_g(), mimetype='text/event-stream')



def svUpdateListener_cb(subscriber, parameter, asdu):
    svID = lib61850.SVSubscriber_ASDU_getSvId(asdu).decode("utf-8")
    
    global streamFilter
    if svID not in streamFilter:
        print_to_log("DEBUG: filter not matched for svID: " + svID)
        return

    #print_to_log("SMV event: (svID: %s)" % svID)
    global smv_data
    global sec_counter
    global oldSmpCnt

    seconds = sec_counter[svID]
    size = lib61850.SVSubscriber_ASDU_getDataSize(asdu)
    smpCnt = lib61850.SVSubscriber_ASDU_getSmpCnt(asdu)
    #print_to_log("  confRev: %u" % lib61850.SVSubscriber_ASDU_getConfRev(asdu))
    #print_to_log("  smpSynch: %u" % lib61850.SVSubscriber_ASDU_getSmpSynch(asdu))

    # list with all y values (4x amp and 4x volt for 9-2 LE)
    indices = {}
    for channel in streamFilter[svID]:
        if channel * 8 < size:
            indices[channel] =  {'y': lib61850.SVSubscriber_ASDU_getINT32(asdu, channel * 8) }
        else:
            print_to_log("ERROR: cannot retrieve channel %i for svID: %s, size = ", (channel,svID,size)) 

    # json list with { x: samplecount, index: [{y:_},{y:_},{y:_},...] }
    smv_data[svID][seconds].append( {'x': smpCnt, 'channels': indices } )

    # increment the secod counter each 4000 sampled, i.e each second
    if oldSmpCnt[svID] > smpCnt: # trigger second increment when the counter loops.(i.e. when the previous smpCnt is higher then the current, we assume we looped around from 4000 to 0)
        global streamInfo
        streamInfo[svID] = {
                             'size': size, 
                             'seconds': seconds, 
                             'svID': str(lib61850.SVSubscriber_ASDU_getSvId(asdu)),
                             'confRev': lib61850.SVSubscriber_ASDU_getConfRev(asdu), 
                             'smpSync': 0,#lib61850.SVSubscriber_ASDU_getSmpSynch(asdu),
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

        #increment counter    
        seconds = seconds + 1
        smv_data[svID][seconds] = [] # create a new list to store the samples
        sec_counter[svID] = seconds
                             
    oldSmpCnt[svID] = smpCnt
    

# make the callback pointer global to prevent cleanup
svUpdateListener = lib61850.SVUpdateListener(svUpdateListener_cb)


def subscribe(receiver, svID, channel, start = True):
    global streamFilter
    global StreamDetails
    global subscribers

    # check if appid already in use in other filters
    inuse = False
    appid = StreamDetails[svID]['appid']
    for key in streamFilter:
        if StreamDetails[key]['appid'] == appid:
            inuse = True

    # if appid not yet subscribed to, subscribe
    if inuse == False:
        global svUpdateListener
        if lib61850.SVReceiver_isRunning(receiver) == True:
            lib61850.SVReceiver_stop(receiver)
        subscriber = lib61850.SVSubscriber_create(None, appid)
        subscribers[appid] = subscriber

        lib61850.SVSubscriber_setListener(subscriber, svUpdateListener, None)
        lib61850.SVReceiver_addSubscriber(receiver, subscriber)
        streamFilter[svID] = set()

        if start == True:
            lib61850.SVReceiver_start(receiver)
            if lib61850.SVReceiver_isRunning(receiver) ==  False:
                print_to_log("Failed to start SMV subscriber. Reason can be that the Ethernet interface doesn't exist or root permission are required.")
                sys.exit(-1)

    # add the filter
    streamFilter[svID].add(channel)

    print_to_log("INFO: SMV subscribed with: %i %s %i" % (appid, svID, channel))


def unsubscribe(receiver, svID, channel, start = True):
    global streamFilter
    global StreamDetails
    global subscribers

    streamFilter[svID].remove(channel)
    if len(streamFilter[svID]) == 0:
        streamFilter.pop(svID) # remove filter
        # check if appid still in use in other filters
        inuse = False
        appid = StreamDetails[svID]['appid']
        for key in streamFilter:
            if StreamDetails[key]['appid'] == appid:
                inuse = True
        if inuse == False:
            if lib61850.SVReceiver_isRunning(receiver) == True:
                lib61850.SVReceiver_stop(receiver)

            lib61850.SVReceiver_removeSubscriber(receiver, subscribers[appid])

            if start == True:
                lib61850.SVReceiver_start(receiver)
                if lib61850.SVReceiver_isRunning(receiver) ==  False:
                    print_to_log("Failed to start SMV subscriber. Reason can be that the Ethernet interface doesn't exist or root permission are required.")
                    sys.exit(-1)
    print_to_log("INFO: SMV %s, %i unsubscribed" % (svID, channel))


def determine_path():
    """Borrowed from wxglade.py"""
    try:
        root = __file__
        if os.path.islink (root):
            root = os.path.realpath (root)
        return os.path.dirname (os.path.abspath (root))
    except:
        print("ERROR: __file__ variable missing")
        sys.exit ()
        

def start ():
    global receiver
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
    
    if len(sys.argv) > 1:
        print_to_log("Set interface id: %s" % sys.argv[1])
        lib61850.SVReceiver_setInterfaceId(receiver, sys.argv[1])
    else:
        print_to_log("Using interface eth0")
        lib61850.SVReceiver_setInterfaceId(receiver, "eth0")

    # general stream listener thread to catch all streams(subscribed and unsubscribed)
    streamListingThread = threading.Thread(target=getSMVStreams, args=(sys.argv[1],-1))
    streamListingThread.start()
    #subs = subscribe(receiver, None, None, "simpleIOGenericIO/LLN0$GO$gcbAnalogValues",str(1))

    application.run(host="0.0.0.0", debug=False, threaded=True) # debug=true will start 2 subscriber threads

    lib61850.SVReceiver_stop(receiver)
    lib61850.SVReceiver_destroy(receiver)


if __name__ == "__main__":
    start()



