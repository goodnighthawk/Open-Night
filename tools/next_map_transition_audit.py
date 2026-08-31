#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from common import PlayerState, TRAFFIC_SIGNAL_ART_STATES, empty_inventory, traffic_signal_state
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid
from grid_world import ObjectDef
import server


CATALOG_PATH = ROOT / "assets/grid_v100/generated_transition_objects.json"
REPORT_PATH = ROOT / "artifacts/next_map_generated_art/next_map_transition_audit.json"
APPROVED = {
    "assets/generated_v4_transitions/source/approved_building_transitions.png",
    "assets/generated_v4_transitions/source/approved_buzzer_and_signal.png",
    "assets/generated_v4_transitions/source/approved_fire_escape_ladder.png",
    "assets/generated_v4_transitions/source/approved_traffic_signal_matrix.png",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class Socket:
    remote_address = ("127.0.0.1", 0)

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


def session_at(x: float, y: float) -> server.ClientSession:
    return server.ClientSession(
        websocket=Socket(),
        player=PlayerState(player_id="transition-audit", name="Transition Audit", x=x, y=y),
        phone="15550000000",
        inventory=empty_inventory(),
    )


async def interaction_audit(world) -> dict:
    by_kind = {
        kind: next(item for item in world.objects if item.get("interaction_kind") == kind and (
            item.get("demo_only") or item.get("test_area") == "approved_transition_demo"
        ))
        for kind in ("entrance_door", "entrance_buzzer", "roof_access_door", "elevator_transition")
    }
    door = by_kind["entrance_door"]
    session = session_at(*world.object_interaction_point(door))
    require(await server.process_grid_transition_interaction(
        session, requested_object_id=str(door["object_id"])
    ), "entrance door hook did not run")
    require(session.player.interior_id == "approved_transition_demo_interior", "entrance did not enter its interior")

    buzzer = by_kind["entrance_buzzer"]
    session.player.interior_id = ""
    session.player.x, session.player.y = world.object_interaction_point(buzzer)
    before = len(session.websocket.messages)
    require(await server.process_grid_transition_interaction(
        session, requested_object_id=str(buzzer["object_id"])
    ), "buzzer hook did not run")
    buzzer_notice = session.websocket.messages[-1]
    require(len(session.websocket.messages) == before + 1 and buzzer_notice.get("interaction") == "entrance_buzzer",
            "buzzer did not publish its locked/scripted interaction hook")

    elevator = next(
        item for item in world.objects
        if item.get("object_id") == "approved_transition_demo_elevator_ground"
    )
    session.player.x, session.player.y = world.object_interaction_point(elevator)
    require(await server.process_grid_transition_interaction(
        session, requested_object_id=str(elevator["object_id"]), selected_floor=1
    ), "elevator hook did not run")
    require(session.player.level == 1 and world.circle_roof_walkable(
        session.player.x, session.player.y, 18.0
    ), "elevator did not reach a walkable roof target")

    roof_elevator = next(
        item for item in world.objects
        if item.get("object_id") == "approved_transition_demo_elevator_roof"
    )
    session.player.x, session.player.y = world.object_interaction_point(roof_elevator)
    require(await server.process_grid_transition_interaction(
        session, requested_object_id=str(roof_elevator["object_id"]), selected_floor=0
    ), "roof elevator hook did not run")
    require(session.player.level == 0 and world.walkable_at("ground", session.player.x, session.player.y),
            "elevator did not return to a walkable ground target")

    roof_door = by_kind["roof_access_door"]
    session.player.level = 1
    session.player.x, session.player.y = world.object_interaction_point(roof_door)
    require(await server.process_grid_transition_interaction(
        session, requested_object_id=str(roof_door["object_id"])
    ), "roof-access hook did not run")
    require(session.player.interior_id == "approved_transition_demo_upper_interior",
            "roof-access door did not enter its upper interior")
    require(await server.process_grid_transition_interaction(
        session, requested_object_id=str(roof_door["object_id"])
    ), "roof-access return hook did not run")
    require(not session.player.interior_id and session.player.level == 1,
            "roof-access door did not return to rooftop")

    ladder = next(item for item in world.objects if item.get("test_area") == "approved_transition_demo"
                  and item.get("interaction_kind") == "fire_escape_ladder")
    session.player.interior_id = ""
    session.player.level = 0
    session.player.x, session.player.y = world.cell_center(int(ladder["gx"]), int(ladder["gy"]))
    require(server.request_grid_fire_escape(session) == "roof", "ladder did not reach the roof")
    require(server.request_grid_fire_escape(session) == "ground", "ladder did not return to ground")
    return {
        "entrance": "PASS", "buzzer": "PASS", "roof_access": "PASS",
        "elevator_floors": [0, 1], "ladder_levels": [0, 1],
    }


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        load_ground_grid.cache_clear()
        world = load_ground_grid()
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        require(set(catalog["approved_masters"]) == APPROVED, "catalog used an unapproved transition master")
        require(tuple(catalog["traffic_signal_states"]) == TRAFFIC_SIGNAL_ART_STATES,
                "traffic matrix state order is incorrect")

        requested = {
            "entrance_door", "roof_access_door", "elevator_transition", "entrance_buzzer",
            "fire_escape_ladder", *TRAFFIC_SIGNAL_ART_STATES,
        }
        require(requested <= set(catalog["objects"]), "transition catalog is incomplete")
        loaded: dict[str, pygame.Surface] = {}
        for asset_id in requested:
            definition = world.catalog.object(asset_id)
            require(definition.image.startswith("assets/generated_v4_transitions/"),
                    f"transition override escaped the approved output pack: {asset_id}")
            image = pygame.image.load(str(ROOT / definition.image)).convert_alpha()
            require(image.get_at((0, 0)).a == 0, f"{asset_id} is not tightly transparent at its corner")
            require(pygame.mask.from_surface(image, 1).count() > 0, f"{asset_id} contains no artwork")
            require(definition.optional, f"{asset_id} does not fail gracefully when optional art is absent")
            loaded[asset_id] = image

        signal_sizes = {loaded[state].get_size() for state in TRAFFIC_SIGNAL_ART_STATES}
        signal_pivots = {
            (world.catalog.object(state).pivot_x_px, world.catalog.object(state).pivot_y_px)
            for state in TRAFFIC_SIGNAL_ART_STATES
        }
        require(len(signal_sizes) == 1 and len(signal_pivots) == 1,
                "traffic states do not share one canvas and pivot")
        require(all(world.catalog.object(state).native_width_px == 128 and
                    world.catalog.object(state).native_height_px == 176
                    for state in TRAFFIC_SIGNAL_ART_STATES), "traffic runtime scale changed between states")

        # The six-state scripted test signal must actually visit every approved
        # combination; ordinary intersections still use lawful phase-derived states.
        signal = world.data["traffic_signals"][0]
        cycle = float(signal["signal_cycle_seconds"])
        sampled = {
            traffic_signal_state(signal, cycle * (index + 0.25) / 6.0 - float(signal["signal_cycle_offset"]))
            for index in range(6)
        }
        require(sampled == set(TRAFFIC_SIGNAL_ART_STATES), f"demo cycle missed states: {sampled}")

        transition_objects = [item for item in world.objects if item.get("interaction_kind")]
        require(transition_objects and all(float(item.get("collision_radius_px", -1)) == 0
                                           for item in transition_objects),
                "transition artwork gained movement collision")
        require(all(float(item.get("interaction_radius_px", 0)) > 0 for item in transition_objects),
                "transition interaction zones were not serialized separately")
        require(all(str(item.get("interaction_prompt", "")).strip() for item in transition_objects),
                "a transition is missing its interaction prompt")
        require(world.catalog.object("entrance_buzzer").native_width_px * 3 <=
                world.catalog.object("entrance_door").native_width_px,
                "entrance buzzer is not compact relative to the door")
        require(world.catalog.object("fire_escape_ladder").native_width_px <
                world.catalog.object("entrance_door").native_width_px,
                "ladder-only fire escape is not narrow")

        # Alias overrides keep existing maps functional while the canonical IDs
        # are adopted by the new generator.
        for old_id, new_id in (
            ("placeholder_street_door", "entrance_door"),
            ("placeholder_roof_hatch", "roof_access_door"),
            ("placeholder_fire_escape", "fire_escape_ladder"),
        ):
            require(world.catalog.object(old_id).image == world.catalog.object(new_id).image,
                    f"legacy transition alias did not resolve to approved art: {old_id}")

        renderer = GridRenderer(world)
        for rotation in (0, 90, 180, 270):
            rotated = [renderer.catalog_object_at_pivot(state, rotation=rotation) for state in TRAFFIC_SIGNAL_ART_STATES]
            require(all(item is not None for item in rotated), f"traffic state failed to render at {rotation} degrees")
            require(len({(item[0].get_size(), item[1]) for item in rotated if item is not None}) == 1,
                    f"traffic state swap flickers or moves at {rotation} degrees")
        world.catalog.objects["audit_missing_optional"] = ObjectDef(
            object_id="audit_missing_optional", image="assets/generated_v4_transitions/not_present.png",
            native_width_px=16, native_height_px=16, optional=True,
        )
        require(renderer._scaled_object_surface("audit_missing_optional", 16, 16).get_bounding_rect().width == 0,
                "missing optional transition art did not fail gracefully")
        world.catalog.objects.pop("audit_missing_optional", None)

        require(len(world.data.get("traffic_signals", [])) == 4, "test intersection is incomplete")
        require(len({tuple(row["pos"]) for row in world.data["traffic_signals"]}) == 4,
                "test signal fixtures overlap")
        require(all(float(row.get("collision_radius_px", -1)) == 0
                    for row in world.data["traffic_signals"]), "signals gained lane/path collision")
        network_map = server.network_map_payload(server.ACTIVE_MAP)
        require(len(network_map.get("traffic_signals", [])) >= 4,
                "server map serialization omitted the transition test intersection")
        json.dumps(world.data)
        hooks = asyncio.run(interaction_audit(world))

        counts = Counter(str(item.get("interaction_kind")) for item in transition_objects)
        report = {
            "status": "PASS", "release_version_changed": False,
            "approved_masters": sorted(APPROVED), "catalog_objects": len(catalog["objects"]),
            "traffic_states": list(TRAFFIC_SIGNAL_ART_STATES),
            "traffic_canvas_px": list(next(iter(signal_sizes))),
            "traffic_pivot_px": list(next(iter(signal_pivots))),
            "runtime_interactions": dict(counts), "hooks": hooks,
            "demo_signal_count": len(world.data["traffic_signals"]),
            "serialization": world.data["transition_demo"]["serialization"],
            "collision": "art=none; triggers=independent",
            "backward_compatibility": "catalog aliases + optional transparent fallback",
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "NEXT_MAP_TRANSITION_AUDIT_OK",
            f"objects={len(catalog['objects'])}", f"states={len(sampled)}",
            f"canvas={next(iter(signal_sizes))}", f"pivot={next(iter(signal_pivots))}",
            f"interactions={dict(counts)}", "hooks=door+buzzer+roof+elevator+ladder",
            "serialization=pass compatibility=pass",
        )
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
