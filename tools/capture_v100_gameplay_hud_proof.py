#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame
import v100_runtime_refinement
v100_runtime_refinement.install()
import v100_client

OUT = ROOT / "assets" / "grid_v100" / "GAMEPLAY_HUD_RUNTIME_PROOF_1280x720.png"
OVERVIEW = ROOT / "assets" / "grid_v100" / "GROUND_REFINED_RUNTIME_OVERVIEW_2560x1440.png"
AUDIT = ROOT / "assets" / "grid_v100" / "GAMEPLAY_HUD_RUNTIME_AUDIT.json"
# GTA2 reference frames keep the player small relative to roads and expose
# multiple neighboring structures.  Use a deliberately wide proof transform
# while the underlying world normalization is being evaluated.
PROOF_ZOOM = 0.38


def main() -> None:
    game_client = v100_client.game_client
    game_client.NetworkClient.start = lambda self: None
    v100_client.install_v100_client()
    game = game_client.Game("ws://runtime-proof.invalid:8765", "5550000100", "RuntimeProof")
    if game.grid_world is None or game.grid_renderer is None:
        raise RuntimeError("canonical v1.0 client did not initialize GridWorld")

    buildings = {str(item["building_id"]): item for item in game.grid_world.data["building_synthesis"]["buildings"]}
    fires = [item for item in game.grid_world.objects if str(item.get("asset")) == "placeholder_fire_escape"]
    lamps = [item for item in game.grid_world.objects if item.get("lighting_kind") == "sidewalk_lamp"]
    shifted_fires = [fire for fire in fires if buildings.get(str(fire.get("building_id")), {}).get("center_shift_cells") not in (None, [0, 0])]
    if not shifted_fires or not lamps:
        raise RuntimeError("HUD proof requires a centered building, exterior fire escape and synchronized streetlamps")

    def cell_distance(a: dict, b: dict) -> int:
        return abs(int(a["gx"]) - int(b["gx"])) + abs(int(a["gy"]) - int(b["gy"]))

    choices = [(cell_distance(fire, lamp), fire, lamp) for fire in shifted_fires for lamp in lamps if cell_distance(fire, lamp) > 0]
    _distance, target_fire, target_lamp = min(choices, key=lambda row: row[0])
    midpoint_x = (int(target_fire["gx"]) + int(target_lamp["gx"]) + 1.0) * game.grid_world.cell_px * 0.5
    midpoint_y = (int(target_fire["gy"]) + int(target_lamp["gy"]) + 1.0) * game.grid_world.cell_px * 0.5
    x, y = game.grid_world.nearest_walkable("ground", midpoint_x, midpoint_y, game_client.PLAYER_RADIUS)
    local = game_client.RemotePlayer({"id":"runtime-proof-local","name":"RuntimeProof","x":x,"y":y,"aim":-1.5707963267948966,"cash":420,"packages":2,"level":0,"pose":"idle","appearance":None})
    game.local_id = local.id
    game.players = {local.id: local}
    game.map_players = {local.id: {"id":local.id,"name":local.name,"x":x,"y":y,"level":0}}
    game.notice = "v1.0 proportion proof — wide GTA2-like context + HUD + M map"
    game.notice_until = 10**12

    game.camera_zoom = PROOF_ZOOM
    display_surface = game.screen
    view_size = game.logical_view_size()
    game.camera_controller.update((x,y),(view_size[0]//2,view_size[1]//2),view_size,(game.grid_world.world_w,game.grid_world.world_h),1.0/60.0,force_center=True)
    world_surface = pygame.Surface(view_size).convert()
    game.screen = world_surface
    game._render_camera_override = None
    game.draw_world()
    game.draw_player(local, True)
    game.screen = display_surface
    pygame.transform.smoothscale(world_surface, display_surface.get_size(), display_surface)
    game.draw_player_nameplates(); game.draw_job_location_labels(); game.draw_hud()
    zoom = game.tiny_font.render(f"ZOOM {game.camera_zoom:.2f}x", True, game_client.MUTED_TEXT)
    game.screen.blit(zoom,(game.screen.get_width()-zoom.get_width()-18,48))
    rotation = game.tiny_font.render(f"ROT {game.camera_rotation_degrees % 360:05.1f}°", True, game_client.MUTED_TEXT)
    game.screen.blit(rotation,(game.screen.get_width()-rotation.get_width()-18,64))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gameplay_frame = game.screen.copy(); pygame.image.save(gameplay_frame, OUT)
    game.screen.blit(gameplay_frame,(0,0)); game.map_open=True; game.draw_world_map(); mmap_frame=game.screen.copy(); game.map_open=False

    raw_overview=pygame.Surface((2560,1440)).convert(); game.grid_renderer.draw_overview(raw_overview,"ground")
    review=pygame.Surface((2560,1440)).convert(); review.fill((12,12,14))
    review.blit(pygame.transform.smoothscale(gameplay_frame,(1280,720)),(0,0))
    review.blit(pygame.transform.smoothscale(mmap_frame,(1280,720)),(1280,0))
    review.blit(pygame.transform.smoothscale(raw_overview,(2560,720)),(0,720))
    pygame.image.save(review,OVERVIEW)

    refinement=dict(game.grid_world.data.get("runtime_refinement") or {})
    audit={"proof":"canonical_v100_gameplay_hud_and_m_map","screen_px":list(game.screen.get_size()),"camera_zoom":PROOF_ZOOM,"grid_cell":list(game.grid_world.world_to_cell(x,y)),"m_map_capture":True,"review_board_panels":["wide_gameplay_hud","actual_M_map","full_ground_overview"],"proportion_reference":"GTA2 overhead gameplay — multiple neighboring buildings visible around player","proof_target":{"building_id":str(target_fire.get("building_id","")),"fire_escape_cell":[int(target_fire["gx"]),int(target_fire["gy"])],"lamp_id":str(target_lamp.get("lighting_id","")),"lamp_cell":[int(target_lamp["gx"]),int(target_lamp["gy"])],"fire_to_lamp_cell_distance":cell_distance(target_fire,target_lamp)},"hud_calls":["Game.draw_hud","Game.draw_local_minimap","Game.draw_player","Game.draw_player_nameplates","Game.draw_world_map"],"grid_authority":True,"runtime_refinement":refinement}
    if refinement.get("centered_building_count") != 8: raise RuntimeError(f"building-centering runtime audit failed: {refinement}")
    if refinement.get("fire_escape_outside_collision_count") != 25: raise RuntimeError(f"fire-escape runtime audit failed: {refinement}")
    if refinement.get("street_lamp_asset_sync_count",0) < 40: raise RuntimeError(f"streetlamp runtime audit failed: {refinement}")
    AUDIT.write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(audit,indent=2,sort_keys=True))

if __name__ == "__main__": main()
