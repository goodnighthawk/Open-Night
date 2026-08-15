from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import statistics
import time
import sys
from dataclasses import dataclass, field
from pathlib import Path

from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_settings() -> dict[str, str]:
    path = ROOT / "config" / "stress_test.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {str(row.get("key", "")).strip(): str(row.get("value", "")).strip() for row in csv.DictReader(f) if row.get("key")}


def fval(cfg, key, default):
    try: return float(cfg.get(key, default))
    except Exception: return float(default)


def ival(cfg, key, default):
    try: return int(float(cfg.get(key, default)))
    except Exception: return int(default)


@dataclass
class BotStats:
    sent: int = 0
    received: int = 0
    snapshots: int = 0
    notices: int = 0
    interactions: int = 0
    vehicle_actions: int = 0
    inventory_requests: int = 0
    errors: int = 0
    connected: bool = False
    latencies_ms: list[float] = field(default_factory=list)


BEHAVIORS = ("wander", "shop", "vehicle", "bicycle", "idle")


def choose_behavior(rng: random.Random, cfg: dict[str, str]) -> str:
    weights = [max(0.0, fval(cfg, f"{name}_weight", 1.0)) for name in BEHAVIORS]
    if sum(weights) <= 0: return "wander"
    return rng.choices(BEHAVIORS, weights=weights, k=1)[0]


def motion_for(behavior: str, phase: float, rng: random.Random) -> tuple[float, float, bool]:
    if behavior == "idle": return 0.0, 0.0, False
    # Smooth changing vectors mimic real key-held movement better than packet noise.
    angle = phase + (0.35 if behavior == "shop" else 0.0)
    x, y = math.cos(angle), math.sin(angle)
    if behavior in {"vehicle", "bicycle"}:
        return x, y, behavior == "vehicle"
    # walkers occasionally move on one dominant axis like keyboard input.
    if rng.random() < 0.35:
        if abs(x) > abs(y): y = 0.0; x = 1.0 if x >= 0 else -1.0
        else: x = 0.0; y = 1.0 if y >= 0 else -1.0
    return x, y, False


async def drain_until_welcome(ws, stats: BotStats, timeout: float = 8.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end-time.monotonic()))
        stats.received += 1
        try: msg = json.loads(raw)
        except Exception: continue
        if msg.get("type") == "welcome": return True
    return False


async def bot(index: int, cfg: dict[str, str], stop_at: float, connect_delay: float = 0.0) -> BotStats:
    stats = BotStats()
    rng = random.Random(0xB07 + index * 7919)
    if connect_delay > 0: await asyncio.sleep(connect_delay)
    uri = cfg["server_uri"]
    phone = f"555{rng.randint(1000000, 9999999):07d}"[-10:]
    try:
        async with connect(uri, ping_interval=20, ping_timeout=20, open_timeout=8) as ws:
            await ws.send(json.dumps({"type":"hello", "name":f"StressBot{index:03d}", "phone":phone, "client_version":"0.8.0"}))
            stats.sent += 1
            if not await drain_until_welcome(ws, stats):
                stats.errors += 1; return stats
            stats.connected = True

            hz = max(1.0, fval(cfg, "input_hz", 10.0))
            period = 1.0 / hz
            behavior = choose_behavior(rng, cfg)
            behavior_until = time.monotonic() + max(1.0, fval(cfg, "behavior_seconds", 5.0)) * rng.uniform(0.65, 1.35)
            next_interact = time.monotonic() + rng.uniform(0.7, max(1.0, fval(cfg,"interaction_interval_seconds",3.0)))
            next_inventory = time.monotonic() + rng.uniform(4.0, 12.0)
            action_done = False

            while time.monotonic() < stop_at:
                loop_started = time.perf_counter()
                now = time.monotonic()
                if now >= behavior_until:
                    behavior = choose_behavior(rng, cfg)
                    behavior_until = now + max(1.0, fval(cfg, "behavior_seconds", 5.0)) * rng.uniform(0.65, 1.35)
                    action_done = False
                phase = now * 0.72 + index * 0.43
                x, y, boost = motion_for(behavior, phase, rng)
                await ws.send(json.dumps({"type":"input", "x":x, "y":y, "aim":phase, "boost":boost}))
                stats.sent += 1

                if behavior == "shop" and now >= next_interact:
                    await ws.send(json.dumps({"type":"interact"})); stats.sent += 1; stats.interactions += 1
                    next_interact = now + max(0.8, fval(cfg,"interaction_interval_seconds",3.0)) * rng.uniform(0.7,1.4)
                elif behavior in {"vehicle","bicycle"} and not action_done:
                    await ws.send(json.dumps({"type":"car_action"})); stats.sent += 1; stats.vehicle_actions += 1
                    action_done = True
                if now >= next_inventory:
                    await ws.send(json.dumps({"type":"inventory_request"})); stats.sent += 1; stats.inventory_requests += 1
                    next_inventory = now + rng.uniform(8.0, 18.0)

                # Read everything available for one input period. First-message delay is a rough
                # end-to-end response latency metric rather than a protocol ping benchmark.
                first = True
                deadline = time.monotonic() + period
                while time.monotonic() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.001, deadline-time.monotonic()))
                    except asyncio.TimeoutError:
                        break
                    stats.received += 1
                    if first:
                        stats.latencies_ms.append((time.perf_counter()-loop_started)*1000.0); first=False
                    try: msg=json.loads(raw)
                    except Exception: continue
                    kind=msg.get("type")
                    if kind=="snapshot": stats.snapshots += 1
                    elif kind=="notice": stats.notices += 1
    except Exception:
        stats.errors += 1
    return stats


def percentile(values: list[float], p: float) -> float:
    if not values: return 0.0
    vals=sorted(values); idx=min(len(vals)-1,max(0,int(round((len(vals)-1)*p))))
    return vals[idx]


def output_path(cfg: dict[str,str], count: int) -> Path:
    from portable_paths import ensure_shared_layout
    root=ensure_shared_layout()["stress_results"]
    stamp=time.strftime("%Y%m%d_%H%M%S")
    return root / f"stress_{stamp}_{count}bots.csv"


async def run_stage(cfg: dict[str,str], count: int, duration: float) -> dict:
    ramp=max(0.0,fval(cfg,"spawn_ramp_seconds",8.0))
    stop_at=time.monotonic()+duration+ramp
    started=time.perf_counter()
    tasks=[]
    for i in range(count):
        delay=(ramp*i/max(1,count-1)) if count>1 else 0.0
        tasks.append(bot(i,cfg,stop_at,delay))
    results=await asyncio.gather(*tasks)
    elapsed=time.perf_counter()-started
    connected=sum(1 for r in results if r.connected)
    sent=sum(r.sent for r in results); received=sum(r.received for r in results)
    errors=sum(r.errors for r in results)
    lat=[v for r in results for v in r.latencies_ms]
    summary={
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S"),"requested_bots":count,"connected_bots":connected,
        "duration_s":round(elapsed,2),"sent":sent,"received":received,"messages_per_s":round((sent+received)/max(.001,elapsed),2),
        "snapshots":sum(r.snapshots for r in results),"interactions":sum(r.interactions for r in results),
        "vehicle_actions":sum(r.vehicle_actions for r in results),"inventory_requests":sum(r.inventory_requests for r in results),
        "mean_response_ms":round(statistics.mean(lat),2) if lat else 0.0,"p95_response_ms":round(percentile(lat,.95),2),"errors":errors,
    }
    out=output_path(cfg,count)
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summary)); w.writeheader(); w.writerow(summary)
    print(f"Bots connected: {connected}/{count}; messages: {sent+received}; rate: {summary['messages_per_s']:.1f}/s; p95 response: {summary['p95_response_ms']:.1f} ms")
    print(f"Report: {out}")
    return summary


async def main() -> None:
    cfg=load_settings()
    ap=argparse.ArgumentParser(description="Headless real-protocol Python MMO stress clients")
    ap.add_argument("--server",default=cfg.get("server_uri","ws://127.0.0.1:8765"))
    ap.add_argument("--bots",type=int,default=ival(cfg,"bot_count",25))
    ap.add_argument("--duration",type=float,default=fval(cfg,"duration_seconds",60))
    ap.add_argument("--find-limit",action="store_true",help="Ramp through increasingly large bot populations")
    args=ap.parse_args(); cfg["server_uri"]=args.server
    if args.find_limit:
        stages=[10,25,50,75,100,150,200]
        stage_seconds=max(5.0,fval(cfg,"find_limit_stage_seconds",20.0))
        for count in stages:
            result=await run_stage(cfg,count,stage_seconds)
            if result["connected_bots"] < max(1,int(count*.95)) or result["errors"] > max(2,int(count*.05)):
                print(f"Approximate practical limit is below {count} bots under the configured pass criteria.")
                break
    else:
        await run_stage(cfg,max(1,args.bots),max(1.0,args.duration))

if __name__ == "__main__": asyncio.run(main())
