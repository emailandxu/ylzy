
# --- LOG ---
LOG = {"screen":True, "file":True, "log_file":open("./log.txt","a"), "debug":False}
SID_LENGTH = 32

# --- REDIS ---
REDIS_URL = 'redis://localhost:6379/'
REDIS_HOST = "localhost"
REDIS_PORT = 6379

# --- CHANNEL --
CONNECT_CHANNEL = "connect"
DISCONNECT_CHANNEL = "disconnect"
ASR_RESULT_CHANNEL= "result"
AUDIO_CHANNEL = "audios"