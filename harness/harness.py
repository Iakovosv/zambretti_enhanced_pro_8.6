"""Test harness: runs the pyscript module outside Home Assistant."""
import builtins
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta

MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "weather_forecast_v8_3.py")


class FakeDateTime(datetime):
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now


class FakeState:
    def __init__(self):
        self.values = {}
        self.attrs = {}
        self.set_calls = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def getattr(self, key):
        if key in self.attrs:
            return self.attrs[key]
        raise KeyError(key)

    def set(self, entity, value=None, new_attributes=None, **kw):
        self.set_calls.append((entity, value, new_attributes))
        self.values[entity] = value
        if isinstance(new_attributes, dict):
            self.attrs.setdefault(entity, {}).update(new_attributes)


class FakeHass:
    class config:
        elevation = 66.0
        time_zone = "Europe/Athens"


def load():
    st = FakeState()
    builtins.state = st
    builtins.hass = FakeHass
    builtins.time_trigger = lambda *a, **k: (lambda f: f)
    builtins.log = types.SimpleNamespace(
        info=print, warning=print, error=print, debug=print
    )
    sys.modules.pop("wf", None)
    spec = importlib.util.spec_from_file_location("wf", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wf"] = mod
    spec.loader.exec_module(mod)
    mod.datetime = FakeDateTime
    return mod, st
