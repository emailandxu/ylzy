from functools import partial
from datetime import datetime

from config import *

def logx(*args,**kwargs):
    print_screen = print
    print_file = partial(print, file=LOG["log_file"], flush=True)
    if LOG["screen"]:
        __print = print_screen
    elif LOG["file"]:
        __print = print_file
    __print(datetime.now().strftime("%Y-%m-%d %H:%M:%S;"),end="\t")
    __print(*args,**kwargs)

def logx_debug(*args,**kwargs):
    if LOG["debug"]:
        log(*args,**kwargs)

