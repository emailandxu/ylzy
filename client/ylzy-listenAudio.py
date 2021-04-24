import redis
import subprocess
import os
from config import *

rds = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

def recieve_audio():
    pubsub = rds.pubsub()
    pubsub.subscribe(AUDIO_CHANNEL)
    wav = open("temp.wav","wb")
    for item in pubsub.listen():
        if item['type'] == 'message':
            output = item['data']
            sid = output[:SID_LENGTH].decode()
            voiceData = output[SID_LENGTH:]

            print(f"recv from sid:{sid}, size of {len(voiceData)}")
            
            if voiceData == b"EOF":
                print("收到EOF")
                break
            else:
                wav.write(voiceData)
                wav.flush()
        else:
            print(item)
    
    wav.close()



while True:
    a = input("type any thing!")
    recieve_audio()
    os.system("rm -f file.wav")
    p = subprocess.Popen("ffmpeg -f s16le -ar 16k -ac 1 -i temp.wav file.wav",shell=True)
    print(p.communicate())
    os.system("open file.wav")
