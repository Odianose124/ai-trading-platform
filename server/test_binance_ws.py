import asyncio
import websockets


async def test_connection():
    print("Connecting to Binance...")

    websocket = await websockets.connect(
        "wss://stream.binance.com:9443/ws",
        open_timeout=20,
    )

    print("BINANCE WEBSOCKET CONNECTION: OK")

    await websocket.close()


asyncio.run(test_connection())