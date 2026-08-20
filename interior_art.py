from __future__ import annotations

import math
import os
import time
from functools import lru_cache
from pathlib import Path

import pygame

from character_art import draw_character
from interior_layout import (
    EXIT_TILE,
    ROOM_H,
    ROOM_W,
    blocked_tiles,
    building_rect,
    interior_building_id,
    interior_cell_size,
    interior_exit_world,
    interior_floor_rect,
    near_exit,
    tile_center_world,
)


ROOT = Path(__file__).resolve().parent
APPROVED_DIR = ROOT / "assets" / "environment" / "approved"

# The old renderer used an independent 2:1 isometric grid. v1.0 keeps the same
# room presets as authored furniture vocabulary, but renders every surface,
# prop and player in the exterior orthographic X/Y projection.
ROOM_PRESETS = {
    "starter_apartment": {
        "title": "FORT LEE STARTER APARTMENT", "floor": "city_beige_stone_64.png", "wall": "city_red_brick2_64.png", "accent": (170,112,86),
        "f": [("sofa",6,2,(119,72,91)),("coffee",5,3,(112,82,60)),("tv",7,1,(44,51,56)),("bed",2,2,(75,112,145)),("nightstand",1,2,(102,76,57)),("lamp",1,1,(208,166,79)),("counter",7,5,(76,87,89)),("fridge",8,5,(144,151,150)),("table",4,5,(111,80,58)),("plant",8,2,(58,103,64)),("bookshelf",0,3,(84,61,47)),("toilet",8,7,(171,177,174)),("sink",7,7,(139,154,154))],
    },
    "corner_shop": {
        "title": "BRIDGE CORNER STORE", "floor": "city_concrete_64.png", "wall": "city_brown_brick_64.png", "accent": (191,145,72),
        "f": [("counter",6,2,(101,76,57)),("counter",7,2,(101,76,57)),("bookshelf",8,1,(82,60,45)),("bookshelf",8,3,(82,60,45)),("table",4,4,(109,82,57)),("plant",1,1,(57,102,64)),("fridge",7,5,(143,149,148)),("tv",2,2,(46,53,58))],
    },
    "night_diner": {
        "title": "OPEN NIGHT DINER", "floor": "city_beige_stone_64.png", "wall": "city_red_brick_64.png", "accent": (205,82,68),
        "f": [("counter",6,1,(128,64,49)),("counter",7,1,(128,64,49)),("counter",8,1,(128,64,49)),("table",3,3,(107,75,54)),("table",6,4,(107,75,54)),("table",3,6,(107,75,54)),("fridge",8,5,(148,154,151)),("plant",1,1,(55,96,57))],
    },
    "pharmacy": {
        "title": "HUDSON PHARMACY", "floor": "city_gray_stone_64.png", "wall": "city_painted_plaster_64.png", "accent": (87,151,130),
        "f": [("counter",6,2,(70,99,91)),("counter",7,2,(70,99,91)),("bookshelf",2,2,(98,115,109)),("bookshelf",2,4,(98,115,109)),("bookshelf",5,5,(98,115,109)),("fridge",8,5,(154,159,157)),("plant",1,1,(49,101,62))],
    },
    "laundromat": {
        "title": "24 HOUR LAUNDROMAT", "floor": "city_gray_stone_64.png", "wall": "city_painted_plaster_64.png", "accent": (77,133,165),
        "f": [("washer",2,2,(151,158,158)),("washer",3,2,(151,158,158)),("washer",4,2,(151,158,158)),("washer",6,4,(151,158,158)),("washer",7,4,(151,158,158)),("table",4,6,(96,89,77)),("counter",8,1,(75,87,90))],
    },
    "pawn_shop": {
        "title": "PAWN & EXCHANGE", "floor": "city_concrete_64.png", "wall": "city_brown_brick_64.png", "accent": (198,147,68),
        "f": [("counter",6,2,(88,65,50)),("counter",7,2,(88,65,50)),("bookshelf",2,1,(69,54,43)),("bookshelf",2,3,(69,54,43)),("tv",5,4,(40,46,50)),("tv",7,5,(40,46,50)),("lamp",3,5,(196,149,66)),("plant",8,1,(51,88,55))],
    },
    "garage": {
        "title": "RIVERSIDE GARAGE", "floor": "city_concrete_64.png", "wall": "city_gray_stone_64.png", "accent": (187,128,63),
        "f": [("counter",7,1,(75,72,65)),("counter",8,1,(75,72,65)),("bookshelf",1,1,(61,61,58)),("bookshelf",1,3,(61,61,58)),("workbench",5,5,(85,68,52)),("tv",8,5,(41,48,51)),("locker",2,6,(122,128,127))],
    },
    "nightclub": {
        "title": "AFTER HOURS CLUB", "floor": "city_concrete_64.png", "wall": "city_red_brick2_64.png", "accent": (139,72,132),
        "f": [("counter",7,1,(61,48,72)),("counter",8,1,(61,48,72)),("sofa",2,2,(91,47,79)),("sofa",5,4,(63,60,101)),("table",3,5,(84,65,55)),("lamp",1,1,(190,74,139)),("lamp",8,5,(66,154,179)),("plant",7,3,(43,72,53))],
    },
    "warehouse_office": {
        "title": "WAREHOUSE OFFICE", "floor": "city_concrete_64.png", "wall": "city_brown_brick_64.png", "accent": (157,116,66),
        "f": [("counter",6,2,(84,69,55)),("table",3,3,(91,70,53)),("bookshelf",8,1,(65,55,47)),("bookshelf",8,3,(65,55,47)),("tv",5,1,(39,44,47)),("locker",7,6,(130,136,134)),("plant",1,1,(50,82,53))],
    },
    "rooftop_loft": {
        "title": "WASHINGTON HEIGHTS LOFT", "floor": "city_beige_stone_64.png", "wall": "city_red_brick_64.png", "accent": (104,144,174),
        "f": [("sofa",6,2,(73,91,106)),("coffee",5,3,(102,76,58)),("tv",8,1,(40,47,52)),("bed",2,2,(91,112,135)),("nightstand",1,2,(95,70,54)),("lamp",1,1,(207,166,78)),("counter",7,5,(83,92,91)),("fridge",8,5,(146,152,150)),("plant",7,2,(54,100,61)),("bookshelf",2,5,(79,59,46))],
    },
}


@lru_cache(maxsize=24)
def _material(name: str, brightness_key: int = 100) -> pygame.Surface | None:
    path = APPROVED_DIR / str(name)
    if not path.is_file():
        return None
    try:
        surf = pygame.image.load(str(path)).convert()
    except (pygame.error, OSError):
        return None
    if brightness_key != 100:
        overlay = pygame.Surface(surf.get_size())
        overlay.fill((max(0, min(255, brightness_key)),) * 3)
        surf.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    return surf


def _tile_material(target: pygame.Surface, texture: pygame.Surface | None, rect: pygame.Rect, fallback: tuple[int,int,int]) -> None:
    if rect.width <= 0 or rect.height <= 0:
        return
    if texture is None:
        pygame.draw.rect(target, fallback, rect)
        return
    tw, th = texture.get_size()
    old_clip = target.get_clip()
    target.set_clip(rect.clip(target.get_rect()))
    for y in range(rect.top - (rect.top % th), rect.bottom, th):
        for x in range(rect.left - (rect.left % tw), rect.right, tw):
            target.blit(texture, (x, y))
    target.set_clip(old_clip)


def _shade(color: tuple[int,int,int], factor: float) -> tuple[int,int,int]:
    return tuple(max(0, min(255, int(v * factor))) for v in color)


class IsometricInterior:
    """v1.0 world-registered First Floor renderer.

    The class name is retained temporarily for client API compatibility, but no
    isometric coordinate transform exists here. Player/furniture coordinates are
    authoritative world X/Y values inside the bound building footprint, and the
    camera is the same orthographic world projection used outside.
    """

    ROOM_W = ROOM_W
    ROOM_H = ROOM_H

    def __init__(self, map_config: dict | None = None) -> None:
        self.map_config = map_config or {}
        self.active = False
        self.room_id = "starter_apartment"
        self.player_x = 0.0
        self.player_y = 0.0
        self.player_aim = -math.pi / 2.0
        self.player_anim_epoch = time.monotonic()
        self.player_moving_until = 0.0
        self.title = ROOM_PRESETS["starter_apartment"]["title"]
        self.furniture = []
        self.blocked = set()
        self._apply_room_preset(self.room_id)

    def set_map(self, map_config: dict) -> None:
        self.map_config = map_config or {}

    def _apply_room_preset(self, room_id: str) -> None:
        self.room_id = str(room_id)
        preset = ROOM_PRESETS.get(self.room_id, ROOM_PRESETS["starter_apartment"])
        self.title = str(preset["title"])
        self.furniture = list(preset["f"])
        self.blocked = blocked_tiles(self.room_id)

    def enter(self, room_id: str = "starter_apartment", title: str | None = None) -> None:
        self.active = True
        self._apply_room_preset(room_id)
        if title:
            self.title = str(title).upper()
        # Server sync supplies the authoritative world position immediately.
        # This deterministic local fallback avoids a single-frame jump on enter.
        self.player_x, self.player_y = tile_center_world(self.map_config, self.room_id, (2, 6))
        self.player_aim = -math.pi / 2.0
        self.player_anim_epoch = time.monotonic()
        self.player_moving_until = 0.0

    def leave(self) -> None:
        self.active = False

    def set_player_state(self, x: float, y: float, aim: float) -> None:
        nx, ny = float(x), float(y)
        if math.hypot(nx - self.player_x, ny - self.player_y) > 0.25:
            self.player_moving_until = time.monotonic() + 0.16
            self.player_anim_epoch = time.monotonic()
        self.player_x, self.player_y = nx, ny
        self.player_aim = float(aim)

    def handle_key(self, key: int) -> bool:
        """Consume interior controls; movement itself stays server-authoritative."""
        if not self.active:
            return False
        if key == pygame.K_ESCAPE:
            self.leave()
            return True
        if key == pygame.K_e and near_exit(self.map_config, self.room_id, self.player_x, self.player_y):
            self.leave()
            return True
        return key in (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_UP, pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT)

    def _camera(self, surface: pygame.Surface) -> tuple[float, float]:
        sw, sh = surface.get_size()
        return self.player_x - sw * 0.5, self.player_y - sh * 0.5

    def _screen(self, x: float, y: float, camera: tuple[float,float]) -> tuple[int,int]:
        return int(round(float(x) - camera[0])), int(round(float(y) - camera[1]))

    def _floor_screen_rect(self, camera: tuple[float,float]) -> pygame.Rect | None:
        floor = interior_floor_rect(self.map_config, self.room_id)
        if floor is None:
            return None
        x, y, w, h = floor
        sx, sy = self._screen(x, y, camera)
        return pygame.Rect(sx, sy, int(round(w)), int(round(h)))

    def _building_screen_rect(self, camera: tuple[float,float]) -> pygame.Rect | None:
        bid = interior_building_id(self.map_config, self.room_id)
        rect = building_rect(self.map_config, bid)
        if rect is None:
            return None
        x, y, w, h = rect
        sx, sy = self._screen(x, y, camera)
        return pygame.Rect(sx, sy, int(round(w)), int(round(h)))

    def _furniture_rect(self, gx: int, gy: int, camera: tuple[float,float], scale_x: float = .72, scale_y: float = .65) -> pygame.Rect:
        cx, cy = tile_center_world(self.map_config, self.room_id, (gx, gy))
        cw, ch = interior_cell_size(self.map_config, self.room_id)
        sx, sy = self._screen(cx, cy, camera)
        return pygame.Rect(0, 0, max(8, int(cw * scale_x)), max(8, int(ch * scale_y))).copy().move(0,0).inflate(0,0).clamp(pygame.Rect(sx-int(cw), sy-int(ch), int(cw*2), int(ch*2))) if False else pygame.Rect(sx - max(4,int(cw*scale_x/2)), sy - max(4,int(ch*scale_y/2)), max(8,int(cw*scale_x)), max(8,int(ch*scale_y)))

    def _draw_furniture(self, surface: pygame.Surface, kind: str, gx: int, gy: int, color: tuple[int,int,int], camera: tuple[float,float]) -> None:
        rect = self._furniture_rect(gx, gy, camera)
        shadow = rect.move(3, 4)
        pygame.draw.rect(surface, (9, 11, 12), shadow, border_radius=3)
        if kind in {"plant", "lamp"}:
            cx, cy = rect.center
            if kind == "plant":
                pygame.draw.rect(surface, (84,61,45), (cx-5, cy+2, 10, max(7, rect.height//3)), border_radius=2)
                for dx, dy in ((-8,-3),(7,-4),(0,-10),(-4,-11),(5,-10)):
                    pygame.draw.ellipse(surface, color, (cx+dx-6, cy+dy-5, 12, 10))
            else:
                pygame.draw.circle(surface, (222,166,78), (cx,cy), max(4,min(rect.width,rect.height)//5))
                glow = pygame.Surface((34,34), pygame.SRCALPHA)
                pygame.draw.circle(glow, (237,174,86,34), (17,17), 16)
                surface.blit(glow, (cx-17,cy-17))
            return
        pygame.draw.rect(surface, _shade(color,.72), rect, border_radius=3)
        inner = rect.inflate(-max(3,rect.width//8), -max(3,rect.height//8))
        pygame.draw.rect(surface, color, inner, border_radius=2)
        pygame.draw.rect(surface, _shade(color,1.18), rect, width=1, border_radius=3)
        if kind in {"tv", "washer", "fridge", "locker"}:
            inset = rect.inflate(-max(5,rect.width//4), -max(5,rect.height//4))
            if kind == "tv":
                pygame.draw.rect(surface, (25,43,53), inset, border_radius=2)
            elif kind == "washer":
                pygame.draw.circle(surface, (45,53,55), inset.center, max(4,min(inset.width,inset.height)//3), width=2)
            else:
                pygame.draw.line(surface, (42,47,47), (rect.centerx,rect.top+3),(rect.centerx,rect.bottom-3),1)
        elif kind in {"sofa", "bed"}:
            pygame.draw.line(surface, _shade(color,1.25), (rect.left+4, rect.centery), (rect.right-4, rect.centery), 2)
        elif kind in {"bookshelf", "counter", "workbench"}:
            for off in range(rect.left+5, rect.right-3, max(6,rect.width//4)):
                pygame.draw.line(surface, _shade(color,.55), (off,rect.top+3),(off,rect.bottom-3),1)

    def _draw_room(self, surface: pygame.Surface, camera: tuple[float,float]) -> None:
        preset = ROOM_PRESETS.get(self.room_id, ROOM_PRESETS["starter_apartment"])
        building = self._building_screen_rect(camera)
        floor = self._floor_screen_rect(camera)
        if building is None or floor is None:
            return
        pygame.draw.rect(surface, (19,18,18), building)
        floor_tex = _material(str(preset["floor"]), 62)
        wall_tex = _material(str(preset["wall"]), 56)
        _tile_material(surface, floor_tex, floor, (55,52,48))

        # Paint wall thickness *inside* the authoritative footprint. Door/exit
        # opening is cut at the registered EXIT_TILE position.
        wall = max(7, min(14, int(min(building.width, building.height) * .035)))
        strips = [
            pygame.Rect(building.left,building.top,building.width,wall),
            pygame.Rect(building.left,building.bottom-wall,building.width,wall),
            pygame.Rect(building.left,building.top,wall,building.height),
            pygame.Rect(building.right-wall,building.top,wall,building.height),
        ]
        for strip in strips:
            _tile_material(surface, wall_tex, strip, (73,55,48))
        pygame.draw.rect(surface, (123,105,88), building, width=2)
        pygame.draw.rect(surface, (23,25,25), floor, width=2)

        # Subtle floor joints preserve world scale and provide movement feedback.
        cw, ch = interior_cell_size(self.map_config, self.room_id)
        floor_world = interior_floor_rect(self.map_config, self.room_id)
        if floor_world:
            fx,fy,fw,fh = floor_world
            for gx in range(1,ROOM_W):
                sx,_ = self._screen(fx+gx*cw,fy,camera)
                pygame.draw.line(surface,(103,96,83),(sx,floor.top),(sx,floor.bottom),1)
            for gy in range(1,ROOM_H):
                _,sy = self._screen(fx,fy+gy*ch,camera)
                pygame.draw.line(surface,(103,96,83),(floor.left,sy),(floor.right,sy),1)

        # Exit remains a dynamic/gameplay marker, not a fake texture-only door.
        ex, ey = interior_exit_world(self.map_config, self.room_id)
        esx, esy = self._screen(ex,ey,camera)
        door_w = max(18,int(cw*.55))
        pygame.draw.rect(surface,(24,29,30),(esx-door_w//2, floor.bottom-wall-3, door_w, wall+6))
        pygame.draw.line(surface, preset["accent"], (esx-door_w//2,esy),(esx+door_w//2,esy),2)

        # Furniture is drawn from the same authoring cells used by server
        # collision, transformed through the same building-floor registration.
        for kind,gx,gy,color in self.furniture:
            self._draw_furniture(surface,kind,int(gx),int(gy),tuple(color),camera)

        # Warm practical pools are restrained and purely cosmetic.
        lights = [item for item in self.furniture if item[0] == "lamp"]
        for _,gx,gy,_ in lights:
            lx,ly = tile_center_world(self.map_config,self.room_id,(int(gx),int(gy)))
            sx,sy = self._screen(lx,ly,camera)
            glow=pygame.Surface((96,96),pygame.SRCALPHA)
            pygame.draw.circle(glow,(235,170,83,20),(48,48),46)
            pygame.draw.circle(glow,(235,170,83,18),(48,48),27)
            surface.blit(glow,(sx-48,sy-48))

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font, appearance: dict | None = None, occupants: list[dict] | None = None) -> None:
        surface.fill((7,9,11))
        camera = self._camera(surface)
        self._draw_room(surface,camera)

        occupants = occupants or [{
            "name":"YOU", "appearance":appearance, "x":self.player_x, "y":self.player_y,
            "aim":self.player_aim, "moving":time.monotonic()<self.player_moving_until,
            "anim_time":time.monotonic()-self.player_anim_epoch, "local":True, "bubble":None,
        }]
        # Same world-depth convention as outdoors: larger Y draws later.
        for occ in sorted(occupants,key=lambda row:float(row.get("y",0.0))):
            sx,sy=self._screen(float(occ.get("x",0.0)),float(occ.get("y",0.0)),camera)
            draw_character(
                surface,(sx,sy),float(occ.get("aim",0.0)),occ.get("appearance"),
                scale=0.82,local_ring=None,moving=bool(occ.get("moving",False)),
                animation="walk" if occ.get("moving") else "idle",anim_time=float(occ.get("anim_time",0.0)),mode="topdown",
            )
            name=small_font.render(str(occ.get("name","")),True,(232,231,224))
            surface.blit(name,(sx-name.get_width()//2,sy-36))
            bubble=occ.get("bubble")
            if isinstance(bubble,dict) and bubble.get("text"):
                text=small_font.render(str(bubble.get("text",""))[:48],True,(24,24,24))
                box=text.get_rect(midbottom=(sx,sy-43)).inflate(12,8)
                pygame.draw.rect(surface,(235,231,216),box,border_radius=5)
                pygame.draw.rect(surface,(42,42,40),box,width=1,border_radius=5)
                surface.blit(text,text.get_rect(center=box.center))

        preset=ROOM_PRESETS.get(self.room_id,ROOM_PRESETS["starter_apartment"])
        title=font.render(self.title,True,(236,232,216))
        surface.blit(title,(24,20))
        bid=interior_building_id(self.map_config,self.room_id)
        sub=small_font.render(f"FIRST FLOOR · WORLD REGISTERED · {bid}",True,(150,154,151))
        surface.blit(sub,(24,48))
        hint="WASD move · E at exit · Esc leave"
        h=small_font.render(hint,True,(173,174,166))
        surface.blit(h,(24,surface.get_height()-30))
