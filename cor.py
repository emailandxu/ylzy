import asyncio
import time
import requests

now = lambda : time.time()

async def do_some_work(x):
    print('Waiting: ', x)
    return await asyncio.get_running_loop().run_in_executor(None ,requests.get, "https://www.baidu.com")


async def main():
    start = now()

    r = await do_some_work(2)
    print(r.text)
    print('TIME: ', now() - start)

main_task = asyncio.ensure_future(main())
loop = asyncio.get_event_loop()
loop.run_until_complete(main_task)