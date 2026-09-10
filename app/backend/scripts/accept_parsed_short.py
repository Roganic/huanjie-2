"""Play the actual model-produced short module, without editing its output.

Usage: python scripts/accept_parsed_short.py /absolute/parser-result.json
Runs only deterministic rules in disposable sessions; no paid model requests.
"""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

runtime = Path(tempfile.mkdtemp(prefix="huanjie-parsed-short-"))
os.environ.update(SESSION_STATE_DIR=str(runtime / "sessions"), SAVE_DIR=str(runtime / "saves"),
                  MODULE_DIR=str(runtime / "modules"), DRAFT_DIR=str(runtime / "drafts"), GM_ENABLED="false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from httpx import AsyncClient, ASGITransport
from src.main import app
from src import state
from src.content.compiler import flag
from src.game.commands import facts

source_file = Path(sys.argv[1]).resolve()
generated = json.loads(source_file.read_text())
report = {"complete": False, "input_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
          "source_file": str(source_file), "routes": [], "steps": [], "checks": []}
report_file = runtime / "report.json"
roll = [20]


def one(values, predicate):
    found = [v for v in values if predicate(v)]
    assert len(found) == 1, f"Expected one mechanism; found {[v.get('name', v.get('id')) for v in found]}"
    return found[0]


async def main():
    assert generated["valid"] and generated.get("module"), "Parser did not produce a valid module"
    graph, pack = generated["outline"], generated["module"]
    people = graph["people"]
    giver = one(people, lambda p: p["name"] == "岑婆")
    apprentice = one(people, lambda p: p["name"] == "阿禾")
    beats = graph["beats"]
    persuade = one(beats, lambda b: b.get("trigger") == "check" and b.get("skill") == "persuasion")
    investigate = one(beats, lambda b: b.get("trigger") == "check" and b.get("skill") == "investigation")
    assert persuade.get("dc", 10) == investigate.get("dc", 10) == 10
    restore = one(beats, lambda b: b.get("trigger") == "interact" and any(d["beat_id"] == investigate["id"] and d.get("outcome") == "failure" for d in b.get("requires", [])))
    assert restore.get("time_cost", 1) > investigate.get("time_cost", 1)
    assert restore["success"].get("delay", 0) == 0
    lighthouse = one(graph["locations"], lambda p: p["name"] == "灯塔")
    calibration_sources = {persuade['id'], investigate['id'], restore['id']}
    light = one(beats, lambda b: b["scene_id"] == lighthouse["id"] and b["trigger"] == "interact" and
                calibration_sources <= {d['beat_id'] for d in b.get('requires_any', [])})
    bells = [b for b in beats if b["scene_id"] == lighthouse["id"] and b["trigger"] == "interact" and "钟" in b["name"]]
    assert bells, "The story needs an automatic bell route"
    # Exercise the ordinary bell action even after the deadline. An optional
    # late-only variant must not make the main action lead to the wrong ending.
    bell = min(bells, key=lambda b: len(b.get("requires", [])) + len(b.get("requires_any", [])))
    timers = [b for b in beats if b["success"].get("delay", 0) == 10]
    timer = one(timers, lambda b: b["trigger"] == "talk" and b.get("target_id") == giver["id"])
    assert timer["success"].get("scope") in ("story", "region")
    cancellations = {d["beat_id"] for d in timer["success"].get("cancel_after", [])}
    assert {light["id"], bell["id"]} <= cancellations
    quest = one(graph["quests"], lambda q: q["giver_id"] == giver["id"])
    assert quest["xp_reward"] == 80
    medal = one(graph["items"], lambda i: "纪念章" in i["name"])
    report["checks"].append("DC10双检定、失败复原操作耗时、交谈启动10格全局倒计时及两种取消条件")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        bootstrap = (await client.get("/state/bootstrap")).json()["session_id"]
        assert (await client.post("/character/create", headers={"X-Session-Id": bootstrap}, json={"name": "解析验收旅人", "character_class": "warrior"})).status_code == 200
        assert (await client.post("/modules/import", json=pack)).status_code == 200
        for route in ("social", "investigation", "failure", "bell", "late_light", "late_bell"):
            activated = await client.post("/modules/activate", headers={"X-Session-Id": bootstrap}, json={"module_id": pack["id"]})
            assert activated.status_code == 200
            sid = activated.json()["session_id"]
            headers = {"X-Session-Id": sid}
            def session(): return state._get_session(sid, False)
            async def act(kind, target):
                body = {"kind": kind, "target_id": target, "request_id": f"generated-{len(report['steps'])}", "expected_scene_id": session().scene.id}
                response = await client.post("/commands", headers=headers, json=body)
                assert response.status_code == 200, response.text
                result = response.json()["result"]
                report["steps"].append({"route": route, "kind": kind, "target": target, "result": result,
                    "world_time": session().event_clock.world_seconds, "flags": session().content_flags.copy()})
                report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
                assert result.get("action_status") != "blocked", result
                settled = facts(session())
                replay = await client.post("/commands", headers=headers, json=body)
                assert replay.json()["replayed"] and facts(session()) == settled
                return result
            async def travel(destination):
                queue = [(session().scene.id, [])]
                visited = set()
                while queue:
                    here, route_steps = queue.pop(0)
                    if here == destination:
                        for step in route_steps: await act("move", step)
                        return
                    if here in visited: continue
                    visited.add(here)
                    for exit in pack["scenes"][here]["exits"]:
                        queue.append((exit["target_scene_id"], [*route_steps, exit["target_scene_id"]]))
                raise AssertionError("Generated route cannot reach destination")
            roll[0] = 20
            await act("talk", giver["id"])
            active_timers = [e for e in session().scheduled_events.values() if e.id == timer["id"]]
            assert len(active_timers) == 1 and active_timers[0].status == "scheduled", "First conversation must arm timer"
            assert active_timers[0].due - active_timers[0].created_at == 600
            if route.startswith("late"):
                # Repeated conversation does not advance the world's action clock.
                # Delay through actual travel, without completing either navigation route.
                nearby = pack['scenes'][giver['scene_id']]['exits'][0]['target_scene_id']
                for _ in range(6):
                    await travel(nearby)
                    await travel(giver['scene_id'])
                assert flag(timer["id"]) in session().content_flags
            if route in ("social", "late_light"):
                await travel(apprentice["scene_id"])
                await act("challenge", persuade["id"])
                assert flag(persuade["id"]) in session().content_flags
            elif route in ("investigation", "failure"):
                roll[0] = 1 if route == "failure" else 20
                await travel(investigate["scene_id"])
                result = await act("challenge", investigate["id"])
                assert result["outcome"] == ("failure" if route == "failure" else "success")
                if route == "failure":
                    before = facts(session())
                    saved = (await client.post("/save", headers=headers)).json()
                    state._sessions.clear()
                    assert (await client.post("/load", json={"save_id": saved["save_id"]})).status_code == 200
                    assert facts(session()) == before
                    start = session().event_clock.world_seconds
                    await act("interact", restore["id"])
                    assert session().event_clock.world_seconds - start == restore["time_cost"] * 60
                    assert flag(restore["id"]) in session().content_flags
            await travel(lighthouse["id"])
            use_bell = route in ("bell", "late_bell")
            navigation = bell if use_bell else light
            await act("interact", navigation["id"])
            assert flag(navigation["id"]) in session().content_flags, "Navigation should settle on operation"
            if not route.startswith("late"):
                assert session().scheduled_events[timer["id"]].status == "cancelled"
            await travel(giver["scene_id"])
            await act("talk", giver["id"])
            expected = "等到天亮" if route.startswith("late") else "听见归航" if use_bell else "雾里的光"
            assert session().adventure_outcome and session().adventure_outcome["title"] == expected, (route, session().adventure_outcome)
            assert session().actor.experience_points == 80
            assert sum(i.id == medal["id"] for i in session().actor.inventory) == 1
            await act("talk", giver["id"])
            assert session().actor.experience_points == 80 and sum(i.id == medal["id"] for i in session().actor.inventory) == 1
            report["routes"].append({"route": route, "ending": expected, "xp": 80, "medals": 1})
    report["complete"] = True


try:
    with patch("src.engine.dice.roll_d20", lambda: roll[0]): asyncio.run(main())
except Exception as error:
    report["error"] = f"{type(error).__name__}: {error}"
    raise
finally:
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(str(report_file), flush=True)
