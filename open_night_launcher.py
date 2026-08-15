from __future__ import annotations

import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

APP_TITLE = (
    "OPEN NIGHT // WORK IN PROGRESS MAP"
    if os.getenv("OPEN_NIGHT_MAP_PREVIEW", "").strip()
    else "OPEN NIGHT // Launcher"
)
WINDOW = (1120, 820)
FPS = 60

BG = (12, 13, 11)
PANEL = (23, 25, 20)
PANEL_2 = (31, 34, 27)
CREAM = (226, 218, 185)
MUTED = (137, 141, 121)
LIME = (174, 216, 65)
YELLOW = (238, 197, 59)
RED = (204, 59, 47)
ROAD = (43, 46, 41)
ROAD_EDGE = (77, 79, 65)
BLOCK = (32, 36, 30)
BLOCK_EDGE = (50, 55, 45)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.08):
            return True
    except OSError:
        return False


class LaunchButton:
    def __init__(self, pg, rect, number, title, subtitle, action):
        self.pg = pg
        self.rect = pg.Rect(rect)
        self.number = number
        self.title = title
        self.subtitle = subtitle
        self.action = action
        self.hover = False
        self.flash_until = 0.0

    def handle(self, event):
        if event.type == self.pg.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == self.pg.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.flash_until = time.monotonic() + 0.18
            return self.action
        return None

    def draw(self, screen, fonts):
        pg = self.pg
        hot = self.hover or time.monotonic() < self.flash_until
        fill = (45, 49, 37) if hot else PANEL_2
        edge = LIME if hot else (83, 89, 69)
        pg.draw.rect(screen, fill, self.rect, border_radius=3)
        pg.draw.rect(screen, edge, self.rect, 2, border_radius=3)
        pg.draw.rect(screen, YELLOW if hot else (105, 105, 82), (self.rect.x, self.rect.y, 8, self.rect.h))
        num = fonts['number'].render(self.number, True, YELLOW if hot else MUTED)
        screen.blit(num, (self.rect.x + 22, self.rect.y + 13))
        title = fonts['button'].render(self.title, True, CREAM)
        screen.blit(title, (self.rect.x + 76, self.rect.y + 11))
        sub = fonts['small'].render(self.subtitle, True, LIME if hot else MUTED)
        screen.blit(sub, (self.rect.x + 77, self.rect.y + 42))


class OpenNightLauncher:
    def __init__(self, pg):
        self.pg = pg
        self.root = Path(__file__).resolve().parent
        self.screen = pg.display.set_mode(WINDOW, pg.RESIZABLE)
        pg.display.set_caption(APP_TITLE)
        self.clock = pg.time.Clock()
        self.fonts = {
            'logo': pg.font.SysFont('impact', 96),
            'tag': pg.font.SysFont('consolas', 18, bold=True),
            'button': pg.font.SysFont('consolas', 23, bold=True),
            'small': pg.font.SysFont('consolas', 14),
            'number': pg.font.SysFont('impact', 32),
            'status': pg.font.SysFont('consolas', 15, bold=True),
        }
        self.status = "READY // choose a system"
        self.status_kind = 'ok'
        self.status_until = 0.0
        self.spawned = []
        self.map_cars = [
            [0.12, 0, 0.16], [0.45, 1, 0.11], [0.77, 0, 0.14], [0.22, 1, 0.18], [0.63, 0, 0.09]
        ]
        self.buttons = []
        self._layout_buttons()
        self.last_ports = 0.0
        self.server_online = False
        self.web_online = False

    def _layout_buttons(self):
        x, y, w, h, gap = 596, 126, 480, 78, 12
        specs = [
            ('01', 'MAP GENERATOR', 'semantic map + cosmetics + lighting', self.launch_map_generator),
            ('02', 'QUICK TEST', 'memory server + protocol gate + client', self.launch_quick_test),
            ('03', 'START SERVER', 'authoritative server • portable .map + cache', self.launch_server),
            ('04', 'DESKTOP CLIENT', 'auto-detects Railway internet + LAN servers', self.launch_desktop),
            ('05', 'WEB CLIENT', 'pygbag browser client on localhost:8000', self.launch_web),
            ('06', 'MOVEMENT PREVIEW', 'character sprite + camera/action sandbox', self.launch_character_preview),
            ('07', 'MAP VIEWER', 'open portable .map without starting a server', self.launch_map_viewer),
        ]
        self.buttons = [LaunchButton(self.pg, (x, y+i*(h+gap), w, h), *spec) for i, spec in enumerate(specs)]

    def _set_status(self, message, kind='ok', seconds=8):
        self.status = message
        self.status_kind = kind
        self.status_until = time.monotonic() + seconds

    def _new_console(self, bat: Path, env=None):
        if not bat.is_file():
            raise FileNotFoundError(bat)
        flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
        cmd = ['cmd.exe', '/c', str(bat)] if os.name == 'nt' else ['bash', str(bat)]
        proc = subprocess.Popen(cmd, cwd=str(bat.parent), env=env, creationflags=flags)
        self.spawned.append(proc)
        return proc

    def _python_process(self, script: Path, *args):
        py = self.root/'.venv'/'Scripts'/'python.exe'
        if not py.is_file():
            py = Path(sys.executable)
        flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
        proc = subprocess.Popen([str(py), str(script), *map(str, args)], cwd=str(self.root), creationflags=flags)
        self.spawned.append(proc)
        return proc

    def launch_map_generator(self):
        try:
            env = os.environ.copy()
            env['OPEN_NIGHT_GAME_ROOT'] = str(self.root)
            self._new_console(self.root/'dev_tools'/'map_generator'/'MAP_GENERATOR.bat', env=env)
            self._set_status('MAP GENERATOR v0.5.1 // screenshot traces // night + street lamps // portable .map')
        except Exception as exc:
            self._set_status(f'MAP GENERATOR FAILED // {exc}', 'error')

    def launch_quick_test(self):
        try:
            self._new_console(self.root/'QUICK_LOCAL_TEST.bat')
            self._set_status('QUICK TEST // protocol-supervised local test launched')
        except Exception as exc:
            self._set_status(f'QUICK TEST FAILED // {exc}', 'error')

    def launch_server(self):
        try:
            self._new_console(self.root/'RUN_SERVER.bat')
            self._set_status('SERVER // starting on websocket port 8765')
        except Exception as exc:
            self._set_status(f'SERVER FAILED // {exc}', 'error')

    def launch_desktop(self):
        try:
            self._new_console(self.root/'RUN_CLIENT.bat')
            self._set_status('DESKTOP // client launched')
        except Exception as exc:
            self._set_status(f'DESKTOP FAILED // {exc}', 'error')

    def launch_web(self):
        try:
            self._new_console(self.root/'RUN_WEB_CLIENT.bat')
            self._set_status('WEB // pygbag build/server launched on port 8000')
        except Exception as exc:
            self._set_status(f'WEB FAILED // {exc}', 'error')

    def launch_character_preview(self):
        try:
            script = self.root/'dev_tools'/'character_preview'/'sprite_tester.py'
            pack = self.root/'assets'/'characters'/'master_dual_camera'
            self._python_process(script, pack)
            self._set_status('MOVEMENT PREVIEW // using the game authoritative character pack')
        except Exception as exc:
            self._set_status(f'PREVIEW FAILED // {exc}', 'error')

    def launch_map_viewer(self):
        try:
            self._python_process(self.root/'map_viewer.py')
            self._set_status('MAP VIEWER // opened the current default playable map')
        except Exception as exc:
            self._set_status(f'MAP VIEWER FAILED // {exc}', 'error')

    def _update_ports(self):
        if time.monotonic() - self.last_ports > 0.8:
            self.server_online = port_open(8765)
            self.web_online = port_open(8000)
            self.last_ports = time.monotonic()

    def _draw_city(self, surf, t):
        pg = self.pg
        w, h = surf.get_size()
        pg.draw.rect(surf, BG, (0, 0, w, h))
        # Original overhead industrial-city motif: deliberately abstract, not copied game art.
        scale = max(0.7, min(1.4, w/1120))
        ox = int(34*scale); oy = int(74*scale)
        for gx in range(-1, 5):
            for gy in range(-1, 6):
                x = ox + int(gx*128*scale)
                y = oy + int(gy*105*scale)
                r = pg.Rect(x, y, int(95*scale), int(73*scale))
                pg.draw.rect(surf, BLOCK, r)
                pg.draw.rect(surf, BLOCK_EDGE, r, max(1,int(scale)))
                # rooftop details
                rr = r.inflate(-int(30*scale), -int(26*scale))
                pg.draw.rect(surf, (38,42,35), rr)
        # two roads and dashed centers
        vr = pg.Rect(int(238*scale), 0, int(70*scale), h)
        hr = pg.Rect(0, int(368*scale), int(560*scale), int(74*scale))
        pg.draw.rect(surf, ROAD, vr); pg.draw.rect(surf, ROAD, hr)
        pg.draw.line(surf, ROAD_EDGE, (vr.left,0), (vr.left,h), 2)
        pg.draw.line(surf, ROAD_EDGE, (vr.right,0), (vr.right,h), 2)
        for yy in range(-30, h+30, int(44*scale)):
            pg.draw.rect(surf, (126,119,77), (vr.centerx-2, yy, 4, int(19*scale)))
        for xx in range(-30, int(560*scale), int(44*scale)):
            pg.draw.rect(surf, (126,119,77), (xx, hr.centery-2, int(19*scale), 4))
        # moving top-down car slivers
        for i, car in enumerate(self.map_cars):
            phase, axis, speed = car
            p = (phase + t*speed) % 1.0
            c = RED if i % 2 == 0 else YELLOW
            if axis == 0:
                x = vr.centerx + (-14 if i%3 else 13)
                y = int(p*h)
                pg.draw.rect(surf, c, (x-5, y-11, 10, 22), border_radius=2)
            else:
                x = int(p*min(w*0.52, 580*scale)); y = hr.centery + (13 if i%2 else -13)
                pg.draw.rect(surf, c, (x-11, y-5, 22, 10), border_radius=2)
        # vignette overlays
        shade = pg.Surface((w,h), pg.SRCALPHA)
        shade.fill((0,0,0,62))
        pg.draw.rect(shade, (0,0,0,0), (24,65,int(520*scale),int(570*scale)))
        surf.blit(shade,(0,0))

    def _draw_logo(self, surf):
        pg = self.pg
        logo = self.fonts['logo'].render('OPEN NIGHT', True, CREAM)
        shadow = self.fonts['logo'].render('OPEN NIGHT', True, RED)
        x, y = 42, 80
        surf.blit(shadow, (x+7,y+7)); surf.blit(logo,(x,y))
        # grime/glitch cuts through the word to evoke a rough late-90s crime-game UI without copying a logo.
        for yy, ww in ((128,140),(162,220),(198,105)):
            pg.draw.rect(surf, BG, (x+28, yy, ww, 3))
        tag = self.fonts['tag'].render('// CITY SYSTEM CONTROL', True, LIME)
        surf.blit(tag,(48,202))
        pg.draw.rect(surf, YELLOW, (48,238,290,4))
        pg.draw.rect(surf, RED, (345,238,62,4))

    def _draw_status(self, surf):
        pg = self.pg
        w,h = surf.get_size()
        box = pg.Rect(34, h-66, w-68, 40)
        pg.draw.rect(surf, PANEL, box)
        pg.draw.rect(surf, (68,73,58), box, 1)
        col = RED if self.status_kind == 'error' else LIME
        msg = self.fonts['status'].render(self.status, True, col)
        surf.blit(msg,(box.x+15,box.y+11))
        online = f"SERVER {'ONLINE' if self.server_online else 'OFF'}   WEB {'ONLINE' if self.web_online else 'OFF'}"
        osurf = self.fonts['small'].render(online, True, CREAM)
        surf.blit(osurf,(box.right-osurf.get_width()-14, box.y+12))

    def draw(self):
        w,h = self.screen.get_size()
        canvas = self.pg.Surface(WINDOW)
        self._draw_city(canvas, time.monotonic())
        # main right control slab
        self.pg.draw.rect(canvas, (12,13,11,225), (565,72,530,590))
        self.pg.draw.rect(canvas, (83,89,69), (565,72,530,590), 2)
        head = self.fonts['tag'].render('OPEN NIGHT // DEVELOPMENT LAUNCHER', True, YELLOW)
        canvas.blit(head,(596,90))
        self._draw_logo(canvas)
        for b in self.buttons: b.draw(canvas,self.fonts)
        self._draw_status(canvas)
        hint = self.fonts['small'].render('ESC quits launcher // launched systems keep running', True, MUTED)
        canvas.blit(hint,(42,260))
        if (w,h) != WINDOW:
            canvas = self.pg.transform.smoothscale(canvas,(w,h))
        self.screen.blit(canvas,(0,0))
        self.pg.display.flip()

    def run(self):
        running = True
        while running:
            for event in self.pg.event.get():
                if event.type == self.pg.QUIT: running=False
                elif event.type == self.pg.KEYDOWN and event.key == self.pg.K_ESCAPE: running=False
                else:
                    # map mouse coordinates back to design resolution when resized
                    actual_event = event
                    if hasattr(event,'pos') and self.screen.get_size()!=WINDOW:
                        sx = WINDOW[0]/self.screen.get_width(); sy=WINDOW[1]/self.screen.get_height()
                        d = event.dict.copy(); d['pos']=(int(event.pos[0]*sx),int(event.pos[1]*sy))
                        actual_event = self.pg.event.Event(event.type,d)
                    for b in self.buttons:
                        action = b.handle(actual_event)
                        if action: action()
            self._update_ports()
            self.draw()
            self.clock.tick(FPS)
        return 0


def main():
    try:
        import pygame
    except ImportError:
        print('pygame-ce is required. Start with START_OPEN_NIGHT.bat so setup can install dependencies.', file=sys.stderr)
        return 2
    pygame.init()
    try:
        return OpenNightLauncher(pygame).run()
    finally:
        pygame.quit()


if __name__ == '__main__':
    raise SystemExit(main())
