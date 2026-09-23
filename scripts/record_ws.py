"""Record every /ws message from a running Herald server to JSONL (UI fixtures).

    python scripts/record_ws.py ws://127.0.0.1:8101/ws ui/public/fixtures/stroke_demo.jsonl
Stop with Ctrl+C. Each line is {"t_ms": <ms since start>, "msg": <message>}. Synthetic scenarios only:
never record real patient data or anyone's voice.
"""
import asyncio
import json
import sys
import time

import websockets


async def main(url: str, out: str) -> None:
    t0 = time.monotonic()
    n = 0
    async with websockets.connect(url, max_size=None) as ws:
        with open(out, "w") as f:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "pong":
                    continue
                f.write(json.dumps({"t_ms": round((time.monotonic() - t0) * 1000), "msg": msg}) + "\n")
                f.flush()
                n += 1
                print(f"\r{n} messages", end="", file=sys.stderr)


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1], sys.argv[2]))
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
