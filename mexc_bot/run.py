import asyncio, os, re, yaml
from trader import LiveTrader


def load_config(path: str = "config.yml") -> dict:
    with open(path) as f:
        raw = yaml.safe_load(f)

    def expand(val: str):
        if isinstance(val, str):
            return re.sub(r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), m.group(0)), val)
        return val

    cfg = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            cfg[k] = {kk: expand(vv) for kk, vv in v.items()}
        else:
            cfg[k] = expand(v)
    return cfg

if __name__ == "__main__":
    cfg = load_config()
    asyncio.run(LiveTrader(cfg).run())
