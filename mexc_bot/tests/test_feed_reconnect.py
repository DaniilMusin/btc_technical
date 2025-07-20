import importlib
import asyncio
import os
import sys
import types
import json

# stub heavy matplotlib modules
mpl = types.ModuleType("matplotlib")
mpl.pyplot = types.ModuleType("pyplot")
mpl.dates = types.ModuleType("dates")
mpl.ticker = types.ModuleType("ticker")
mpl.ticker.FuncFormatter = lambda *a, **k: None
sys.modules.setdefault("matplotlib", mpl)
sys.modules.setdefault("matplotlib.pyplot", mpl.pyplot)
sys.modules.setdefault("matplotlib.dates", mpl.dates)
sys.modules.setdefault("matplotlib.ticker", mpl.ticker)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)


ws_stub = types.ModuleType("websockets")
class DummyClosed(Exception):
    pass
ws_stub.ConnectionClosedError = DummyClosed
ws_stub.ConnectionClosedOK = DummyClosed
sys.modules["websockets"] = ws_stub

feed = importlib.import_module("core.feed")
StreamingDataFeed = feed.StreamingDataFeed

class DummyWS:
    def __init__(self, messages):
        self._messages = list(messages)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def send(self, msg):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._messages:
            return self._messages.pop(0)
        raise DummyClosed()


def test_feed_reconnect(monkeypatch):
    os.environ["USE_TESTNET"] = "true"
    os.environ["EXCHANGE"] = "BINGX"

    candles = []

    messages = [
        json.dumps({"data": {"event": "kline", "t": 0, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}}),
        json.dumps({"data": {"event": "kline", "t": 60000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}}),
        json.dumps({"data": {"event": "kline", "t": 120000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}}),
    ]
    call = {"n": 0}

    def dummy_connect(url):
        idx = call["n"]
        call["n"] += 1
        data = [messages[idx]] if idx < len(messages) else []
        return DummyWS(data)

    orig_sleep = asyncio.sleep
    async def dummy_sleep(_):
        await orig_sleep(0)

    monkeypatch.setattr(feed, "websockets", ws_stub)
    monkeypatch.setattr(ws_stub, "connect", lambda url: dummy_connect(url), raising=False)
    monkeypatch.setattr(feed.asyncio, "sleep", dummy_sleep)

    feed_instance = StreamingDataFeed("BTCUSDT", "1m")

    async def on_candle(df):
        candles.append(df)

    async def runner():
        try:
            await asyncio.wait_for(feed_instance.start(on_candle), timeout=0.05)
        except asyncio.TimeoutError:
            pass

    asyncio.run(runner())

    assert len(candles) == 3
