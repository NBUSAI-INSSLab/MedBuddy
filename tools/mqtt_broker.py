"""本地 MQTT Broker（仅用于开发验证，基于 amqtt）。"""
import asyncio
import logging

from amqtt.broker import Broker

logging.basicConfig(level=logging.WARNING)

CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:1883", "max_connections": 50}},
    "sys_interval": 0,
    "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
    "topic-check": {"enabled": False},
}


async def main():
    broker = Broker(CONFIG)
    await broker.start()
    print("broker listening on 127.0.0.1:1883", flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
