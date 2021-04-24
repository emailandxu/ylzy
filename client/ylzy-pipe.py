import redis
import sys
from threading import Thread
import time, json
from config import *

rds = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

 # assign the sid
sid = "1" * SID_LENGTH
config = {
        "language_code":"cmn-CN",
        "sample_rate":"16000"
    }

# register the client
print(f"register client {sid}")
rds.publish(CONNECT_CHANNEL, json.dumps({"sid":sid, "config":config}))


def feed(voiceData, sid):
    # json doesn't support serialize bytes
    print( len(voiceData), type(voiceData) )
    rds.publish( AUDIO_CHANNEL, sid.encode() + voiceData )


def show(sid):
    pubsub = rds.pubsub()
    pubsub.subscribe(ASR_RESULT_CHANNEL + sid)
    
    while True:
        item = pubsub.get_message()
        if item is None:
            break
        else:
            print(item)

t = Thread(target=show, args=(sid,))
t.start()

while True:
    b = sys.stdin.buffer.read(4096)
    if len(b) == 0:
        break
    time.sleep(0.1)
    feed(b, sid)


# leave
rds.publish(DISCONNECT_CHANNEL, json.dumps({"sid":sid}))