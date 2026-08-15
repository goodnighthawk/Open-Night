from __future__ import annotations

import math
import time
import pygame

from character_art import draw_character
from interior_layout import (
    EXIT_TILE,
    ROOM_H as INTERIOR_ROOM_H,
    ROOM_W as INTERIOR_ROOM_W,
    START_TILE,
    blocked_tiles,
)


class IsometricInterior:
    """Small Habbo-inspired *layout language* demo using original procedural art.

    The room uses a fixed 2:1 isometric grid, low walls, compact furniture,
    occlusion-friendly sorting, and grid-snapped placement. It intentionally
    doesn't reproduce Habbo assets or room layouts.
    """

    TILE_W = 64
    TILE_H = 32
    ROOM_W = INTERIOR_ROOM_W
    ROOM_H = INTERIOR_ROOM_H

    def __init__(self) -> None:
        self.active = False
        self.room_id = "starter_apartment"
        self.player_x, self.player_y = START_TILE
        self.player_aim = -math.pi / 2.0
        self.player_anim_epoch = time.monotonic()
        self.player_moving_until = 0.0
        self.exit_tile = EXIT_TILE
        self.title = "FORT LEE STARTER APARTMENT"
        self.wall_a = (183, 145, 122)
        self.wall_b = (158, 120, 104)
        self.floor_a = (194, 174, 138)
        self.floor_b = (183, 160, 125)
        self.furniture = []
        self.blocked = set()
        self._apply_room_preset("starter_apartment")

    def _apply_room_preset(self, room_id: str) -> None:
        self.room_id = room_id
        presets = {
            "starter_apartment": {
                "title":"FORT LEE STARTER APARTMENT", "wall":((184,142,133),(151,111,107)), "floor":((195,173,130),(184,159,119)),
                "f":[("sofa",6,2,(139,81,105)),("coffee",5,3,(133,96,68)),("tv",7,1,(53,61,66)),("bed",2,2,(92,138,178)),("nightstand",1,2,(126,91,64)),("lamp",1,1,(222,187,90)),("counter",7,5,(91,105,109)),("fridge",8,5,(178,185,183)),("table",4,5,(137,97,66)),("plant",8,2,(75,137,83)),("bookshelf",0,3,(102,70,50)),("toilet",8,7,(205,211,207)),("sink",7,7,(174,192,192))]},
            "corner_shop": {
                "title":"BRIDGE CORNER STORE", "wall":((190,177,132),(160,148,112)), "floor":((151,164,154),(139,151,143)),
                "f":[("counter",6,2,(122,91,65)),("counter",7,2,(122,91,65)),("bookshelf",8,1,(100,70,48)),("bookshelf",8,3,(100,70,48)),("table",4,4,(137,102,67)),("plant",1,1,(75,137,83)),("fridge",7,5,(176,184,181)),("tv",2,2,(55,63,69))]},
            "night_diner": {
                "title":"OPEN NIGHT DINER", "wall":((166,98,82),(126,78,74)), "floor":((188,170,143),(165,150,128)),
                "f":[("counter",6,1,(151,74,54)),("counter",7,1,(151,74,54)),("counter",8,1,(151,74,54)),("table",3,3,(132,90,60)),("table",6,4,(132,90,60)),("table",3,6,(132,90,60)),("fridge",8,5,(183,190,186)),("plant",1,1,(72,126,73))]},
            "pharmacy": {
                "title":"HUDSON PHARMACY", "wall":((177,194,184),(134,161,151)), "floor":((205,202,183),(188,187,170)),
                "f":[("counter",6,2,(91,126,116)),("counter",7,2,(91,126,116)),("bookshelf",2,2,(124,145,137)),("bookshelf",2,4,(124,145,137)),("bookshelf",5,5,(124,145,137)),("fridge",8,5,(189,194,191)),("plant",1,1,(63,133,79))]},
            "laundromat": {
                "title":"24 HOUR LAUNDROMAT", "wall":((144,167,184),(111,137,156)), "floor":((185,188,184),(165,170,169)),
                "f":[("fridge",2,2,(190,194,191)),("fridge",3,2,(190,194,191)),("fridge",4,2,(190,194,191)),("fridge",6,4,(190,194,191)),("fridge",7,4,(190,194,191)),("table",4,6,(120,112,95)),("counter",8,1,(91,105,109))]},
            "pawn_shop": {
                "title":"PAWN & EXCHANGE", "wall":((150,125,92),(112,91,70)), "floor":((151,142,119),(133,125,106)),
                "f":[("counter",6,2,(108,77,54)),("counter",7,2,(108,77,54)),("bookshelf",2,1,(83,60,43)),("bookshelf",2,3,(83,60,43)),("tv",5,4,(47,54,60)),("tv",7,5,(47,54,60)),("lamp",3,5,(220,175,76)),("plant",8,1,(65,113,70))]},
            "garage": {
                "title":"RIVERSIDE GARAGE", "wall":((126,131,132),(94,101,105)), "floor":((112,113,108),(101,103,101)),
                "f":[("counter",7,1,(91,88,78)),("counter",8,1,(91,88,78)),("bookshelf",1,1,(73,72,67)),("bookshelf",1,3,(73,72,67)),("table",5,5,(105,83,58)),("tv",8,5,(49,57,60)),("fridge",2,6,(153,158,157))]},
            "nightclub": {
                "title":"AFTER HOURS CLUB", "wall":((102,75,126),(74,58,93)), "floor":((94,89,105),(80,76,92)),
                "f":[("counter",7,1,(73,55,85)),("counter",8,1,(73,55,85)),("sofa",2,2,(111,54,95)),("sofa",5,4,(74,70,126)),("table",3,5,(103,78,64)),("lamp",1,1,(224,86,163)),("lamp",8,5,(83,189,222)),("plant",7,3,(53,93,68))]},
            "warehouse_office": {
                "title":"WAREHOUSE OFFICE", "wall":((137,128,113),(105,98,88)), "floor":((137,136,127),(120,120,114)),
                "f":[("counter",6,2,(103,83,62)),("table",3,3,(113,84,59)),("bookshelf",8,1,(78,62,49)),("bookshelf",8,3,(78,62,49)),("tv",5,1,(46,52,55)),("fridge",7,6,(166,171,169)),("plant",1,1,(65,106,67))]},
            "rooftop_loft": {
                "title":"WASHINGTON HEIGHTS LOFT", "wall":((175,154,132),(139,117,105)), "floor":((184,166,143),(167,149,129)),
                "f":[("sofa",6,2,(90,112,131)),("coffee",5,3,(126,91,66)),("tv",8,1,(48,56,62)),("bed",2,2,(112,140,166)),("nightstand",1,2,(117,84,61)),("lamp",1,1,(231,188,86)),("counter",7,5,(103,111,110)),("fridge",8,5,(181,187,184)),("plant",7,2,(70,132,80)),("bookshelf",2,5,(97,68,49))]},
        }
        p = presets.get(room_id, presets["starter_apartment"])
        self.title = p["title"]
        self.wall_a, self.wall_b = p["wall"]
        self.floor_a, self.floor_b = p["floor"]
        self.exit_tile = EXIT_TILE
        self.furniture = list(p["f"])
        self.blocked = blocked_tiles(room_id)

    def enter(self, room_id: str = "starter_apartment", title: str | None = None) -> None:
        self.active = True
        self._apply_room_preset(room_id)
        if title:
            self.title = str(title).upper()
        self.player_x, self.player_y = START_TILE
        self.player_aim = -math.pi / 2.0
        self.player_anim_epoch = time.monotonic()
        self.player_moving_until = 0.0

    def leave(self) -> None:
        self.active = False

    def set_player_state(self, x: int, y: int, aim: float) -> None:
        nx = max(0, min(self.ROOM_W - 1, int(x)))
        ny = max(0, min(self.ROOM_H - 1, int(y)))
        if (nx, ny) != (self.player_x, self.player_y):
            self.player_moving_until = time.monotonic() + 0.22
            self.player_anim_epoch = time.monotonic()
        self.player_x, self.player_y = nx, ny
        self.player_aim = float(aim)

    def handle_key(self, key: int) -> bool:
        """Return True if the key was consumed by the interior."""
        if not self.active:
            return False
        if key == pygame.K_ESCAPE:
            self.leave()
            return True
        if key == pygame.K_e and (self.player_x, self.player_y) == self.exit_tile:
            self.leave()
            return True
        dx = dy = 0
        if key in (pygame.K_w, pygame.K_UP):
            dy = -1
        elif key in (pygame.K_s, pygame.K_DOWN):
            dy = 1
        elif key in (pygame.K_a, pygame.K_LEFT):
            dx = -1
        elif key in (pygame.K_d, pygame.K_RIGHT):
            dx = 1
        else:
            return False
        nx = max(0, min(self.ROOM_W - 1, self.player_x + dx))
        ny = max(0, min(self.ROOM_H - 1, self.player_y + dy))
        if dx or dy:
            if dx > 0: self.player_aim = 0.0
            elif dx < 0: self.player_aim = math.pi
            elif dy > 0: self.player_aim = math.pi / 2.0
            else: self.player_aim = -math.pi / 2.0
        if (nx, ny) not in self.blocked:
            self.player_x, self.player_y = nx, ny
            self.player_anim_epoch = time.monotonic()
            self.player_moving_until = self.player_anim_epoch + 0.22
        return True

    def _origin(self, surface: pygame.Surface) -> tuple[int, int]:
        w, h = surface.get_size()
        room_px_w = (self.ROOM_W + self.ROOM_H) * self.TILE_W // 2
        return w // 2 - room_px_w // 2 + self.ROOM_H * self.TILE_W // 2, max(110, h // 2 - 130)

    def iso(self, gx: float, gy: float, origin: tuple[int, int]) -> tuple[int, int]:
        ox, oy = origin
        return int(ox + (gx - gy) * self.TILE_W / 2), int(oy + (gx + gy) * self.TILE_H / 2)

    def tile_poly(self, gx: int, gy: int, origin: tuple[int, int]):
        cx, cy = self.iso(gx, gy, origin)
        hw, hh = self.TILE_W // 2, self.TILE_H // 2
        return [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]

    def _draw_box(self, surface, gx, gy, origin, width, depth, height, color):
        # Small isometric cuboid centered on the tile.
        cx, cy = self.iso(gx, gy, origin)
        hw = max(8, int(width * self.TILE_W / 2))
        dh = max(5, int(depth * self.TILE_H / 2))
        top_y = cy - height
        top = [(cx, top_y - dh), (cx + hw, top_y), (cx, top_y + dh), (cx - hw, top_y)]
        left = [top[3], top[2], (top[2][0], top[2][1] + height), (top[3][0], top[3][1] + height)]
        right = [top[1], top[2], (top[2][0], top[2][1] + height), (top[1][0], top[1][1] + height)]
        def shade(c, f): return tuple(max(0, min(255, int(v * f))) for v in c)
        pygame.draw.polygon(surface, shade(color, .70), left)
        pygame.draw.polygon(surface, shade(color, .82), right)
        pygame.draw.polygon(surface, color, top)
        pygame.draw.lines(surface, (32, 32, 33), True, top, 1)

    def _draw_furniture(self, surface, item, gx, gy, color, origin):
        cx, cy = self.iso(gx, gy, origin)
        if item == "sofa":
            self._draw_box(surface, gx, gy, origin, .78, .62, 24, color)
            self._draw_box(surface, gx, gy - .10, origin, .78, .25, 39, tuple(min(255, v + 20) for v in color))
        elif item == "bed":
            self._draw_box(surface, gx, gy, origin, .88, .72, 14, color)
            pygame.draw.ellipse(surface, (222, 224, 213), (cx - 17, cy - 19, 34, 18))
        elif item in {"coffee", "table", "nightstand", "counter"}:
            dims = {"coffee": (.55,.45,12), "table": (.72,.62,22), "nightstand": (.42,.38,22), "counter": (.82,.52,34)}[item]
            self._draw_box(surface, gx, gy, origin, *dims, color)
        elif item == "tv":
            self._draw_box(surface, gx, gy, origin, .62, .28, 36, color)
            pygame.draw.polygon(surface, (36, 59, 73), [(cx-13,cy-37),(cx+16,cy-29),(cx+16,cy-12),(cx-13,cy-20)])
        elif item == "fridge":
            self._draw_box(surface, gx, gy, origin, .52, .52, 58, color)
            pygame.draw.line(surface, (80,84,84), (cx,cy-42),(cx,cy+3),1)
        elif item == "plant":
            self._draw_box(surface, gx, gy, origin, .34, .34, 14, (125,83,58))
            for ang in range(0,360,60):
                dx=int(math.cos(math.radians(ang))*13); dy=int(math.sin(math.radians(ang))*7)
                pygame.draw.ellipse(surface, color, (cx+dx-7, cy-34+dy-5, 14, 10))
        elif item == "bookshelf":
            self._draw_box(surface, gx, gy, origin, .62, .34, 55, color)
            for i in range(3): pygame.draw.line(surface,(54,38,30),(cx-11,cy-42+i*12),(cx+12,cy-35+i*12),2)
        elif item == "lamp":
            pygame.draw.line(surface,(91,76,53),(cx,cy-28),(cx,cy-2),3)
            pygame.draw.polygon(surface,color,[(cx,cy-42),(cx+12,cy-28),(cx-12,cy-28)])
        elif item == "toilet":
            pygame.draw.ellipse(surface,color,(cx-16,cy-23,32,22)); pygame.draw.rect(surface,color,(cx-10,cy-39,20,18))
        elif item == "sink":
            self._draw_box(surface,gx,gy,origin,.48,.36,27,color); pygame.draw.ellipse(surface,(105,136,149),(cx-10,cy-23,20,9))

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
        appearance: dict | None = None,
        occupants: list[dict] | None = None,
    ) -> None:
        if not self.active:
            return
        w, h = surface.get_size()
        surface.fill((31, 29, 31))
        origin = self._origin(surface)

        # Floor: alternating warm neutral tiles, very readable at low resolution.
        for gy in range(self.ROOM_H):
            for gx in range(self.ROOM_W):
                poly = self.tile_poly(gx, gy, origin)
                c = self.floor_a if (gx + gy) % 2 == 0 else self.floor_b
                pygame.draw.polygon(surface, c, poly)
                pygame.draw.lines(surface, (112, 99, 82), True, poly, 1)

        # Low rear/left walls, Habbo-like in readability but procedurally original.
        wall_h = 84
        for gx in range(self.ROOM_W):
            top = self.tile_poly(gx, 0, origin)
            a, b = top[0], top[1]
            pygame.draw.polygon(surface, self.wall_a, [a,b,(b[0],b[1]-wall_h),(a[0],a[1]-wall_h)])
            pygame.draw.line(surface,(58,54,53),(a[0],a[1]-wall_h),(b[0],b[1]-wall_h),2)
            pygame.draw.line(surface,(108,82,72),a,b,2)
        for gy in range(self.ROOM_H):
            top = self.tile_poly(0, gy, origin)
            a, b = top[0], top[3]
            pygame.draw.polygon(surface, self.wall_b, [a,b,(b[0],b[1]-wall_h),(a[0],a[1]-wall_h)])
            pygame.draw.line(surface,(58,54,53),(a[0],a[1]-wall_h),(b[0],b[1]-wall_h),2)
            pygame.draw.line(surface,(101,77,70),a,b,2)

        # Chunky Habbo-like room readability: a framed rear window and dark door.
        wx, wy = self.iso(6, 0, origin)
        window = [(wx-34,wy-68),(wx+30,wy-51),(wx+30,wy-25),(wx-34,wy-42)]
        pygame.draw.polygon(surface,(54,67,78),window)
        pygame.draw.lines(surface,(34,35,37),True,window,3)
        pygame.draw.line(surface,(185,210,218),(wx-1,wy-59),(wx-1,wy-34),2)
        pygame.draw.line(surface,(185,210,218),(wx-31,wy-54),(wx+27,wy-39),2)
        dx, dy = self.iso(1, 0, origin)
        door = [(dx-22,dy-4),(dx+18,dy+6),(dx+18,dy-61),(dx-22,dy-71)]
        pygame.draw.polygon(surface,(65,60,58),door)
        pygame.draw.lines(surface,(31,31,32),True,door,2)

        # Exit tile / doorway.
        pygame.draw.lines(surface, (231, 199, 83), True, self.tile_poly(*self.exit_tile, origin), 3)

        drawables = [(gx+gy, "f", item, gx, gy, color) for item,gx,gy,color in self.furniture]
        if occupants:
            for occupant in occupants:
                gx = max(0, min(self.ROOM_W - 1, int(occupant.get("x", 0))))
                gy = max(0, min(self.ROOM_H - 1, int(occupant.get("y", 0))))
                drawables.append((gx+gy+.5, "p", occupant, gx, gy, (0,0,0)))
        else:
            drawables.append((self.player_x+self.player_y+.5, "p", {
                "name": "Player", "appearance": appearance, "aim": self.player_aim,
                "moving": time.monotonic() < self.player_moving_until,
                "anim_time": time.monotonic() - self.player_anim_epoch, "local": True,
            }, self.player_x, self.player_y, (0,0,0)))
        drawables.sort(key=lambda x: x[0])
        for _, kind, item, gx, gy, color in drawables:
            if kind == "f":
                self._draw_furniture(surface, item, gx, gy, color, origin)
            else:
                cx, cy = self.iso(gx, gy, origin)
                now = time.monotonic()
                draw_character(
                    surface, (cx, cy - 24), float(item.get("aim", 0.0)), item.get("appearance"), scale=2,
                    moving=bool(item.get("moving", False)), anim_time=float(item.get("anim_time", now)),
                    mode="isometric", local_ring=None,
                )
                name_color = (245, 218, 88) if item.get("local") else (105, 190, 245)
                name = small_font.render(str(item.get("name", "Player"))[:18], True, name_color)
                surface.blit(name, name.get_rect(midbottom=(cx, cy - 55)))
                bubble = item.get("bubble")
                if bubble:
                    text = str(bubble.get("text", ""))[:48]
                    label = small_font.render(text, True, (27, 28, 29))
                    box = label.get_rect(midbottom=(cx, cy - 82)).inflate(18, 12)
                    edge = (190, 125, 235) if bubble.get("scope") == "whisper" else (92, 99, 102)
                    pygame.draw.rect(surface, (245, 244, 235), box, border_radius=6)
                    pygame.draw.rect(surface, edge, box, width=2, border_radius=6)
                    surface.blit(label, label.get_rect(center=box.center))

        title = font.render(self.title, True, (244,244,239))
        surface.blit(title, (22, 18))
        help_text = small_font.render("WASD / arrows: move tile   E on yellow tile: exit   Esc: leave", True, (184,187,188))
        surface.blit(help_text, (22, 54))
        if (self.player_x,self.player_y) == self.exit_tile:
            prompt = font.render("[E] EXIT TO STREET", True, (244,217,91))
            surface.blit(prompt, prompt.get_rect(center=(w//2, h-34)))
