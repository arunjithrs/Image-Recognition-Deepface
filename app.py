#!/usr/bin/python

from flask import Flask, request, jsonify, send_from_directory
import base64
from tinydb import TinyDB, Query
import time
import os, signal
import socket
import cv2
import requests
import numpy as np
import json
import argparse
import signal
import logging
import datetime, time
from scipy import spatial
import os
import json
import shutil, sys

import after_response
import subprocess as sp

import socket
import fcntl
import struct
import psutil

import numpy as np
import urllib2

from os import getpid
from sys import argv, exit

from subprocess import Popen
import subprocess
import traceback
from werkzeug.wsgi import ClosingIterator
from gpiozero import LED
from time import sleep

import threading, time
from random import randint

from gpiozero import LED
from time import sleep


# import pyttsx3
# engine = pyttsx3.init()
# engine.say("Hello this is me talking")
# engine.setProperty('rate',120)  #120 words per minute
# engine.setProperty('volume',0.9)
# engine.runAndWait()

# api address
face_api = "http://192.168.43.192:5000/inferImage?returnFaceId=true&detector=yolo&returnFaceLandmarks=true"

parser = argparse.ArgumentParser(description='Home pro security system')
args = parser.parse_args()

#process
extProc = ""
led_open = LED(18)
led_close = LED(4)

#db
visitors = TinyDB('db/visitors.json')

app = Flask(__name__)
after_response.AfterResponse(app)

# initialize database
db = {"names": [], "embeddings": []}
dbtree = ""
reload_flag = False
try:
    # db = json.loads(open('face_data.txt').read())
    with open("face_data.txt", "r+") as f:
        db = json.load(f)
    dbtree = spatial.KDTree(db["embeddings"])
except:
    pass


@app.route("/")
def hello():
    return "Hello world"
    
@app.route("/api/reboot")
def restart():
    print("Rebooting....")
    stop_face_recg()
    global reload_flag
    reload_flag = True

@app.route('/images/<path:path>')
def send_js(path):
    return send_from_directory('images', path)
    
@app.route('/visitors/<path:path>')
def send_visitors(path):
    return send_from_directory('visitors', path)

@app.route("/api/allow")
def allow_permission():
    door_open()
    time.sleep(5)
    door_close()
    return jsonify({"success": True, "message": "True"})

# list all users
@app.route("/api/users")
def list_users():

    #raspi ip
    IP = get_ip_address('wlan0')
    users = TinyDB('db/users.json')
    users_list = users.all();
    for user in users_list:
        user['pro_pic'] = 'http://' + IP + ':5000/images/' + user['name'] + '/' + user['pro_pic']
        print(user['pro_pic'])

    return jsonify(users_list)

@app.route("/api/private")
def private_mod_fetch():
    settings = TinyDB('db/settings.json')
    settings_list = settings.all();
    print(settings_list)
    if(settings_list[0]['private'] == True):
        return jsonify({"success": True, "message": "True"})
    else:
        return jsonify({"success": True, "message": "False"})
    
    return jsonify({"success": False, "message": "False"})
    
@app.route("/api/visitors")
def list_visitors():
    IP = get_ip_address('wlan0')
    visitorsDb = TinyDB("db/visitors.json")
    visitors = visitorsDb.all()
    return_data = [];
    for visitor in visitors:
        item = {};
        item['name'] = json.dumps(visitor['name'])
        item['date'] = visitor['date']
        item['time'] = visitor['time']
        item['pic'] = 'http://' + IP + ':5000/visitors/' + visitor['url']
        
        return_data.append(item)
    print(return_data)
    return jsonify(return_data)
    
@app.route("/api/private/update", methods=['POST'])
def private_mod_update():

    status = request.form["status"];
    settings = TinyDB('db/settings.json')
    settings.update({'private': json.loads(status)})
    return jsonify({"success": True, "message": "Successfully updated"})

# delete user from db
@app.route("/api/delete", methods=['POST'])
def delete_user():

    name = request.form["name"];

    global db
    users = TinyDB('db/users.json')
    User = Query();
    users_list = users.all();
    users.remove(User.name.search(name))

    # find position of name in face db
    index = 0;
    for i in db['names']:
        if(i == name):
            break
        index+=1

    # remove item from db
    db['names'].remove(name);
    db['embeddings'].remove(db['embeddings'][index])

    with open('face_data.txt','w') as att:
        att.write(json.dumps(db))

    # delete imagesdirectory
    shutil.rmtree('images/' + name);
    shutil.rmtree('dbimg/' + name);
    
    stop_face_recg()
    global reload_flag
    reload_flag = True
    return jsonify({"success": True, "message": "User deleted successfully! Plese wait 10 seconds to reload the system."})


@app.route("/api/access", methods=['POST'])
def user_access_permission():
    name = request.form["name"];
    access = request.form['access'];

    users = TinyDB('db/users.json')
    User = Query();
    users.update({'access': json.loads(access)}, User.name == name)

    return jsonify({"success": True, "message": "asdf"})

# save new user
@app.route("/api/user", methods=['GET', 'POST'])
def user():
    if request.method == 'POST':
        
        stop_face_recg()
        
        imageBlob = request.form['image']
        
        name = request.form['name'].rstrip().lstrip()
        access = request.form['access']
        
        # find position of name in db
        flag = False
        for i in db['names']:
            if(i == name):
                flag = True
        if(flag):
            return jsonify({"success": False, "message": "User already exist"})
        
        imgdata = base64.b64decode(imageBlob)

        # save it
        ts = int(time.time())
        filepath = 'images/' + name
        filename = filepath + '/' + str(ts) + '.jpeg'

        if not os.path.isdir(filepath):
            os.mkdir(filepath)

        with open(filename, 'wb+') as f:
            f.write(imgdata)
            
            print(filename)
            enroll.counter = 0
            image = cv2.imread(filename)
            
            key = cv2.waitKey(1) & 0xFF
            
            frame = cv2.resize(image, (int(320), int(240)))
            #frame = image
            r, imgbuf = cv2.imencode(".bmp", frame)
            image = {'pic': bytearray(imgbuf)}

            r = requests.post(face_api, files=image)
            result = r.json()

            count = 0
            if len(result) > 1:

                faces = result[:-1]
                diag = result[-1]['diagnostics']

                for face in faces:
                    rect, embedding = [face[i] for i in ['faceRectangle','faceEmbeddings']]
                    x,y,w,h, confidence = [rect[i] for i in ['left', 'top', 'width', 'height', 'confidence']]
                    
                    if confidence < 0.8:
                        continue

                    return_name = identify_face(embedding)
                    if(return_name == "unknown"):
                        is_entered = enroll(embedding, frame[y:y+h, x:x+w], name);
                        #store it in the db
                        users = TinyDB('db/users.json')
                        users.insert({'name': name, 'access': json.loads(access), 'pro_pic': str(ts) + '.jpeg'})
                        global reload_flag
                        reload_flag = True
                        
                        
                        start_face_recg()
                        return jsonify({"success": True, "message": "User added successfully! Plese wait 10 seconds to reload the system."})
                    else:
                        if return_name != "unknown":
                            
                            start_face_recg()
                            return jsonify({"success": False, "message": "User already exist! Plese wait 10 seconds to reload the system."})
            else:
                start_face_recg()
                return jsonify({"success": False, "message": "Not valid! Plese wait 10 seconds to reload the system."})
    
    start_face_recg()
    return jsonify({"success": False, "message": "Not valid! Plese wait 10 seconds to reload the system."})

# restart server
@app.after_response
def after():
    global reload_flag
    time.sleep(2)
    if(reload_flag):
        os.execl(sys.executable, sys.executable, * sys.argv)

# enroll a new face into db
def enroll(embedding, face, name):
    print("reached entroll")
    global dbtree
    facename = name
    enroll.counter += 1
    if not os.path.exists("dbimg/%s" % (facename)):
        os.makedirs("dbimg/%s" % (facename))

    cv2.imwrite("dbimg/%s/%d.jpg"%(facename,enroll.counter), face)
    db["names"].append(facename)
    db["embeddings"].append(embedding)
    print("Enrolled %s into db!" % facename)

    dbtree = spatial.KDTree(db["embeddings"])

    with open('face_data.txt', 'w') as att:
        att.write(json.dumps(db))

    return "success"

enroll.counter = 0
            
# start and stop facial recognition script
def start_face_recg():
    for process in psutil.process_iter():
        if process.cmdline() == ['python', 'deepface.py']:
            print('Process found. Terminating it.')
            #process.terminate()
            break
    else:
        print('Process not found: starting it.')
        Popen(['python', 'deepface.py'])

def stop_face_recg():
    for process in psutil.process_iter():
        if process.cmdline() == ['python', 'deepface.py']:
            print('Process found. Terminating it.')
            process.terminate()
            break
    else:
        print('Process not found: starting it.')
        #Popen(['python', 'deepface.py'])
    
    time.sleep(5)
        
def restart_face_recg():

    for process in psutil.process_iter():
        if process.cmdline() == ['python', 'deepface.py']:
            print('Process found. Terminating it.')
            process.terminate()
            break
    else:
        print('Process not found: starting it.')
        Popen(['python', 'deepface.py'])

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])

# search for a face in the db
def identify_face(embedding):

    if dbtree != "":
        dist, idx = dbtree.query(embedding)
        name = db["names"][idx]
        
        if dist > (0.4):
            name = "unknown"
    else:
        name = "unknown"
    
    return name


# door close and open functions
def door_open():
    led_open.on()
    led_close.off()

def door_close():
    led_close.on()
    led_open.off()


if __name__ == "__main__":
    restart_face_recg()
    app.run(host='0.0.0.0' , port=5000, debug=False)

