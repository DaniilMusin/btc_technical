import importlib.util
import os
import pytest

from pathlib import Path

BROKER_PATH = Path(__file__).resolve().parents[1] / 'core' / 'broker.py'
spec = importlib.util.spec_from_file_location('broker', BROKER_PATH)
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)

BingxBroker = broker.BingxBroker

EXAMPLE_SECRET = (
    "mheO6dR8ovSsxZQCOYEFCtelpuxcWGTfHw7te326y6jOwq5WpvFQ9JNljoTwBXZGv5It07m9RXSPpDQEK2w"
)
EXAMPLE_SIG = "8D0D3EA9B592BE3678C33332AB13E9102E093E67255921E15A581146C87C272F"
TIMESTAMP = 1696751141337


def test_bingx_sign(monkeypatch):
    monkeypatch.setenv("BINGX_API_SECRET", EXAMPLE_SECRET)
    monkeypatch.setattr(broker.time, "time", lambda: TIMESTAMP / 1000)
    b = BingxBroker()
    params = {"recvWindow": 0, "subAccountString": "abc12345"}
    signed = b._sign(params.copy())
    assert signed["signature"].upper() == EXAMPLE_SIG
    assert signed["timestamp"] == TIMESTAMP

