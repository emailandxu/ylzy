import asyncio
import websockets
import queue
import random
import time
import json
from typing import Any
import redis
from config import *
import numpy as np


rds = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

async def generalHandler(websocket, path):

    async def create_session(websocket, path) -> str:
        """
        create asr session take input below:
        {
            "apikey":"123",
            "config":{
                "language_code":"cmn-CN",
                "sample_rate":"16000"
            }
        }
        """

        sid = ""
        try:
            init_msg = json.loads(await websocket.recv())

            keys = ("apikey", "config")
            is_all_keys_provided = all([k in init_msg for k in keys])
            
            if not is_all_keys_provided:
                raise ValueError(f"not all keys provided for {keys}")

            # assign the sid
            sid = "1" * SID_LENGTH
            config = init_msg["config"]

            # register the client
            rds.publish(CONNECT_CHANNEL, json.dumps({"sid":sid, "config":config}))

        except Exception as e:
            await websocket.send(f"exception occured:{str(e)}")

        finally:
            return sid

    async def destory_session(sid:str):
        rds.publish(DISCONNECT_CHANNEL, json.dumps({"sid":sid}))

    async def consumer_handler(websocket, path, sid):
        async for message in websocket:
            await consumer(message, sid)

    async def producer_handler(websocket, path, sid):
        while True:
            await asyncio.sleep(0.2)

            # message = await producer(sid)
            # await websocket.send(message)

    sid = await create_session(websocket, path)
    acceptable = sid != ""
    
    if not acceptable:
        return 
    
    print(f"accepted session @ sid:{sid}")

    consumer_task = asyncio.ensure_future(
        consumer_handler(websocket, path, sid))
    producer_task = asyncio.ensure_future(
        producer_handler(websocket, path, sid))
    done, pending = await asyncio.wait(
        [consumer_task, producer_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        print("cancel", task)
        task.cancel()
    
    for task in done:
        print("done", task)
    
    await destory_session(sid)


async def consumer(msg, sid):
    try:
        print(len(msg), type(msg))
        voiceData = msg
        # voiceData = msg['voiceData']
    except KeyError as e:
        logx_debug("即将发生键错误，查看发送信息为：")
        logx_debug(len(msg))
        if msg == {}:
            return "client_msg is empty dict!"
        else:
            raise e

    if voiceData is None or len(voiceData)==0:
        return

    if type(voiceData) == type([0]):
        voiceData = np.array(voiceData,np.int8).tobytes()
        logx_debug("将list int8 转 bytes")

    if type(voiceData) == str:
        voiceData = voiceData.encode()
    
    # json doesn't support serialize bytes
    rds.publish(AUDIO_CHANNEL, sid.encode() + voiceData )

async def producer(sid):
    await asyncio.sleep(random.randint(0,10)*0.1 )
    pubsub = rds.pubsub()
    pubsub.subscribe(ASR_RESULT_CHANNEL + sid)

    while True:
        item = pubsub.get_message()
        if item is None:
            break

    output = json.loads(item['data'])
    sid = output["sid"]
    result = output["result"]

    return result





start_server = websockets.serve(generalHandler, "0.0.0.0", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()