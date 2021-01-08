# -*- coding: utf-8 -*-

import socketio, eventlet
import numpy as np
from threading import Thread
import logging
import redis
import json

from diy_log import *
from config import *

rds = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
rds.publish("channel",json.dumps({"msg":"init"}))

client_manager = socketio.RedisManager(REDIS_URL)
sio = socketio.Server(async_mode='eventlet', \
    client_manager=client_manager, \
    cors_allowed_origins="*")
    
app = socketio.WSGIApp(sio)

eventlet.monkey_patch(all=True, os=True, select=True, socket=True, thread=True, time=True) 

#silent socket.io and flask log
logging.getLogger('socketio').setLevel(logging.INFO)

def recieve_asr_result():
    pubsub = rds.pubsub()
    pubsub.subscribe(ASR_RESULT_CHANNEL)

    while True:
        eventlet.sleep(0.05)
        item = pubsub.get_message()
        if item is None:
            continue 

        if item['type'] != "message":
            logx(item)
            continue

        output = json.loads(item['data'])
        sid = output["sid"]
        result = output["result"]
        if result['type'] in ("final"): 
            logx("收到Google解析后的结果{result}个字符".format(result=len(result["result"])), sid, sep=";")
            try:
                sio.emit('server_response', {'data':result["result"], "bg":result["bg"].__str__(), "ed": result["ed"].__str__()}, room=sid)
            except KeyError as e:
                if "disconnected" in str(e):
                    logx("client was disconnected!!") # 客户端断开，不会再向服务器器推送音频，语音识别会话也会因此结束。
                else:
                    raise e
        if result['type'] in ("partial"):
            sio.emit("server_partial_response",{'data':result["result"]}, room=sid)

        elif result['type'] == "error":
            sio.emit('server_response',{'data': "错误："+ result["result"]}, room=sid)

@sio.on('connect_event')
def connected_msg(sid,msg):
    rds.publish(CONNECT_CHANNEL, json.dumps({"sid":sid, "config":msg}))
    sio.emit("connection_established", {'data':"nothing to say, just do it!"})
    logx("连接ID：" + "sid" + "触发connect_event", "收到配置参数：", msg)

@sio.event
def disconnect(sid):
    rds.publish(DISCONNECT_CHANNEL, json.dumps({"sid":sid}))
    logx('disconnect ', sid)

@sio.on('voice_push_event')
def client_msg(sid,msg):
    try:
        voiceData = msg['voiceData']
    except KeyError as e:
        logx_debug("即将发生键错误，查看发送信息为：")
        logx_debug(len(msg))
        if msg == {}:
            return "client_msg is empty dict!"
        else:
            raise e
    if voiceData is None or len(voiceData)==0:
         return
    
    logx_debug("收到"+ str(type(voiceData)) +"块，大小:{voiceData_len} 来自{sid}".format(voiceData_len=len(voiceData),sid=sid))

    if type(voiceData) == type([0]):
        voiceData = np.array(voiceData,np.int8).tobytes()
        logx_debug("将list int8 转 bytes")

    if type(voiceData) == str:
        voiceData = voiceData.encode()

    # json doesn't support serialize bytes
    rds.publish(AUDIO_CHANNEL, sid.encode() + voiceData )
    sio.emit("voice_ack",{"data":"received "+ str(len(voiceData)) + " bytes block, continue to push event"})

    return "client_msg recieved"

def run_server():
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

def run_exp_server():
    eventlet.wsgi.server(eventlet.listen(('', 5555)), app)

def setupRedis():
    pool = eventlet.GreenPool()
    pool.spawn(recieve_asr_result)

if __name__ == '__main__':
    eventlet.spawn(recieve_asr_result)
    run_exp_server()