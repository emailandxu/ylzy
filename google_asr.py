import numpy as np

import queue
from google.cloud import speech
import google
import time
import json
from config import *
from threading import Thread
import redis

"""
{
    "sid":{
        "g_asr":g_asr,
        "thread":t
    }
}
"""
users = {

}

rds = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

def g_asr_thread(sid, g_asr):
    for result in g_asr():
        rds.publish(ASR_RESULT_CHANNEL, json.dumps({"sid":sid,"result": result}))

def user_connect():
    pubsub = rds.pubsub()
    pubsub.subscribe(CONNECT_CHANNEL)
    for item in pubsub.listen():
        if item['type'] == 'message':
            output = json.loads(item['data'])
            sid = output["sid"]
            config = output["config"]

            g_asr = GoogleASR(sid=sid, **config)
            trd = Thread(target=g_asr_thread, args=(sid,g_asr))
            trd.start()

            users[sid] = {"g_asr":g_asr, "thread":trd}

        else:
            print(item)

def user_disconnect():
    pubsub = rds.pubsub()
    pubsub.subscribe(DISCONNECT_CHANNEL)
    for item in pubsub.listen():
        if item['type'] == 'message':
            output = json.loads(item['data'])
            sid = output["sid"]
            del users[sid]
        else:
            print(item)

def recieve_audio():
    pubsub = rds.pubsub()
    pubsub.subscribe(AUDIO_CHANNEL)
    for item in pubsub.listen():
        if item['type'] == 'message':
            output = item['data']
            sid = output[:SID_LENGTH].decode()
            voiceData = output[SID_LENGTH:]
            try:
                g_asr = users[sid]["g_asr"]
                g_asr.voiceQueue.put(voiceData)
            except KeyError as e:
                print("发生键错误，可能是用户未在创建链接时调用connected_msg！")
                print(str(e))
        else:
            print(item)

def run_redis():
    discon_t = Thread(target=user_disconnect)
    recv_audio_t = Thread(target=recieve_audio)
    discon_t.start()
    recv_audio_t.start()
    
    user_connect()

class GoogleASR:
    # --- RETRY ---
    MAX_RETRY = 7
    SEP_DURATION = 20

    def __init__(self,language_code, sample_rate, sid):
        self.streaming_config = GoogleASR.buildConfig(language_code,sample_rate)
        self.sid = sid
        self.voiceQueue = queue.Queue()
        self.audio_generator = GoogleASR.buildAudioGenerator(self.voiceQueue,self.sid)
    
    @classmethod
    def buildConfig(cls,language_code, sample_rate):
        config = speech.types.RecognitionConfig(
            encoding=speech.enums.RecognitionConfig.AudioEncoding.LINEAR16,
            # encoding=speech.enums.RecognitionConfig.AudioEncoding.FLAC,
            sample_rate_hertz=int(sample_rate),
            language_code=language_code,
            max_alternatives=1,
            enable_word_time_offsets=False,
            enable_automatic_punctuation=True)

        streaming_config = speech.types.StreamingRecognitionConfig(
            config=config,
            interim_results=True)

        return streaming_config
    
    @classmethod
    def buildAudioGenerator(cls, voiceQueue, sid):
        timename = time.strftime('%Y-%m-%d_%H:%M:%S',time.localtime(time.time()))
        timeoutCnt = 0
        lastTimeoutTime = time.time()
        while True:
            try:
                chunk = voiceQueue.get(timeout=2)
                if chunk == b"EOF":
                    print("收到EOF")
                    break
                
                # print(f"收到大小为{len(chunk)}")
                
                yield chunk
            except queue.Empty as e:
                print("{self.sid}: 超时重试第{timeoutCnt}次！".format(sid=sid, timeoutCnt=timeoutCnt))
                timeoutTime = time.time()
                timeoutInterval = timeoutTime - lastTimeoutTime
                if timeoutCnt > self.MAX_RETRY and timeoutInterval < self.SEP_DURATION:
                    print("超时重试大于最大重试次数！")
                    break
                else:
                    # 每15秒一个连续超时计数区间，15秒内连续超时次数大于7次终止服务
                    # 如果上一次超时时间间隔超过15秒，重新计算时次数,以此分隔计数区间
                    if timeoutInterval >= 20:
                        print("进入新的连续超时计数区间")
                        lastTimeoutTime = timeoutTime
                        timeoutCnt = 0
                    yield bytes([0,0]) 
                    timeoutCnt += 1

    def _eternal_response(self,client):
        def build_responses():
            # 阻塞直到收到下一个语音包为止，否则会报空包错误
            self.voiceQueue.put(self.voiceQueue.get())
            audio_generator = GoogleASR.buildAudioGenerator(self.voiceQueue,self.sid)
            requests = (speech.types.StreamingRecognizeRequest(audio_content=content) for content in audio_generator)
            responses = client.streaming_recognize(self.streaming_config, requests)
            responses = (r for r in responses if ( r.results and r.results[0].alternatives))
            return responses
        try:
            responses = build_responses()
            for r in responses:
                if r.results and r.results[0].alternatives:
                    yield r
        except google.api_core.exceptions.OutOfRange as e:
            if "305" in str(e):
                print(sid + "超过305秒， 递归","!"*50)
                for r in self._eternal_response(client):
                    yield r
            else:
                raise e

    def __call__(self):
        # voiceQueue = userVoices[sid]['voiceQueue']
        client = speech.SpeechClient()

        output = {"type":"final","result":"声音异常！！！", "bg":"0","ed":"0"}

        cnt = 0
        num_charsprinted = 0

        # last fianl result end time
        last_final_offset = 0

        for response in self._eternal_response(client):
            cnt +=1
            if not response.results:
                continue

            # The `results` list is consecutive. For streaming, we only care about
            # the first result being considered, since once it's `is_final`, it
            # moves on to considering the next utterance.
            result = response.results[0]
            if not result.alternatives:
                continue

            # Display the transcription of the top alternative.
            top_alternative = result.alternatives[0]
            transcript = top_alternative.transcript

            # Display interim results, but with a carriage return at the end of the
            # line, so subsequent lines will overwrite them.
            #
            # If the previous result was longer than this one, we need to #print
            # some extra spaces to overwrite the previous result
            overwrite_chars = ' ' * (num_charsprinted - len(transcript))
            
            result_seconds = 0
            result_nanos = 0

            if result.result_end_time.seconds:
                result_seconds = result.result_end_time.seconds

            if result.result_end_time.nanos:
                result_nanos = result.result_end_time.nanos

            # result end time since audio start
            result_end_time = int((result_seconds * 1000)
                                        + (result_nanos / 1000000))

            if not result.is_final:
                result = transcript + overwrite_chars + "\n"
                print(len(result).__str__() + "个识别字符")
                num_charsprinted = len(transcript)
                output = {"type":"partial","result":result}
            else:
                result = transcript + overwrite_chars
                num_charsprinted = 0
                output = {"type":"final","result":result, "bg":last_final_offset, "ed":result_end_time}
                last_final_offset = result_end_time

            yield output

        if cnt == 0:
            yield output

def put_audio(g_asr):
    with open("/Users/tony/git-repo/ylzy/wavAndTxt/sample.wav","rb") as f:
        while True:
            try:
                b = f.read(409600)
                if len(b) == 0:
                    raise EOFError
                g_asr.voiceQueue.put(b)
                time.sleep(0.05)
            except EOFError as e:
                g_asr.voiceQueue.put("EOF")
                break
        g_asr.voiceQueue.put(f.read())
        g_asr.voiceQueue.put("EOF")

def test():
    from threading import Thread
    g_asr = GoogleASR("en","44100","123abc")
    t = Thread(target=put_audio, args=(g_asr,))
    t.start()
    g_asr.voiceQueue.put(g_asr.voiceQueue.get())
    print("start" + "."*10)

if __name__ == "__main__":
    run_redis()
    

