from __future__ import annotations

from pathlib import Path


PATH = Path("client.py")
text = PATH.read_text(encoding="utf-8")
original = text


def replace_once(old: str, new: str) -> None:
    global text
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one patch anchor, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    'subtitle = self.small_font.render("M close | yellow: you | green: friends | blue: other online players", True, MUTED_TEXT)',
    'subtitle = self.small_font.render("M close | yellow: you | green: friends | blue: players | supplier/buyer: job markers", True, MUTED_TEXT)',
)

world_anchor = '''            if interest_rect.width > 0 and interest_rect.height > 0:
                pygame.draw.rect(self.screen, (116, 164, 186), interest_rect, width=1)

        for pid, marker in self.map_players.items():
'''
world_markers = '''            if interest_rect.width > 0 and interest_rect.height > 0:
                pygame.draw.rect(self.screen, (116, 164, 186), interest_rect, width=1)

        # Job-economy locations are client-side map UI, not baked map text. This
        # keeps labels horizontal/readable and makes supplier/buyer destinations
        # visible regardless of camera rotation or nearby-player interest culling.
        for raw_pos, marker_color, marker_label in (
            (self.map_config.get("supplier_pos", SUPPLIER_POS), SUPPLIER_COLOR, "SUPPLIER"),
            (self.map_config.get("customer_pos", CUSTOMER_POS), CUSTOMER_COLOR, "BUYER"),
        ):
            try:
                p = mp_dynamic(float(raw_pos[0]), float(raw_pos[1]))
            except (TypeError, ValueError, IndexError, KeyError):
                p = None
            if p is not None and map_rect.collidepoint(p):
                pygame.draw.circle(self.screen, (12, 13, 13), p, 8)
                pygame.draw.circle(self.screen, marker_color, p, 6)
                label = self.tiny_font.render(marker_label, True, marker_color)
                label_rect = label.get_rect(midleft=(p[0] + 8, p[1]))
                pygame.draw.rect(self.screen, (18, 21, 22), label_rect.inflate(4, 2), border_radius=2)
                self.screen.blit(label, label_rect)

        for pid, marker in self.map_players.items():
'''
replace_once(world_anchor, world_markers)

mini_anchor = '''        # The compact minimap is deliberately private/friend-focused. The full
        # M map retains the complete online roster for general orientation.
'''
mini_markers = '''        # Supplier and buyer are gameplay destinations, so they remain visible
        # on the private/friend-focused minimap whenever they are in local range.
        for raw_pos, marker_color in (
            (self.map_config.get("supplier_pos", SUPPLIER_POS), SUPPLIER_COLOR),
            (self.map_config.get("customer_pos", CUSTOMER_POS), CUSTOMER_COLOR),
        ):
            try:
                dx = float(raw_pos[0]) - local.render_x
                dy = float(raw_pos[1]) - local.render_y
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            if dx * dx + dy * dy <= (world_radius * 0.94) ** 2:
                marker_pos = (int(radius + dx * scale), int(radius + dy * scale))
                pygame.draw.circle(mini, (18, 24, 28), marker_pos, 7)
                pygame.draw.circle(mini, marker_color, marker_pos, 5)

        # The compact minimap is deliberately private/friend-focused. The full
        # M map retains the complete online roster for general orientation.
'''
replace_once(mini_anchor, mini_markers)

# Keep the physical destination rings in the rotating world, but move all role
# text to the post-rotation display layer.  Text baked into world_surface rotates
# with the camera and becomes hard to read at arbitrary angles.
replace_once(
    '''        self.draw_interior_entries()
        self.draw_location(tuple(self.map_config["supplier_pos"]), SUPPLIER_COLOR, "SUPPLIER", f"BUY ${BUY_PRICE}")
        self.draw_landmarks()
''',
    '''        self.draw_interior_entries()
        self.draw_location(tuple(self.map_config.get("supplier_pos", SUPPLIER_POS)), SUPPLIER_COLOR, "SUPPLIER", f"BUY ${BUY_PRICE}")
        self.draw_location(tuple(self.map_config.get("customer_pos", CUSTOMER_POS)), CUSTOMER_COLOR, "BUYER", f"SELL ${SELL_PRICE}")
        self.draw_landmarks()
''',
)

replace_once(
    '''    def draw_location(self, pos, color, label: str, sublabel: str) -> None:
        sx, sy = self.world_to_screen(*pos)
        pygame.draw.circle(self.screen, color, (sx, sy), 34, width=4)
        pygame.draw.circle(self.screen, color, (sx, sy), 8)
        self.screen.blit(self.small_font.render(label, True, TEXT_COLOR), self.small_font.render(label, True, TEXT_COLOR).get_rect(center=(sx, sy - 52)))
        sub = self.small_font.render(sublabel, True, TEXT_COLOR)
        self.screen.blit(sub, sub.get_rect(center=(sx, sy + 52)))

''',
    '''    def draw_location(self, pos, color, label: str, sublabel: str) -> None:
        # Physical destination rings belong to the world.  Role text is drawn
        # later in draw_job_location_labels() after camera rotation/zoom.
        sx, sy = self.world_to_screen(*pos)
        pygame.draw.circle(self.screen, color, (sx, sy), 34, width=4)
        pygame.draw.circle(self.screen, color, (sx, sy), 8)

    def draw_job_location_labels(self) -> None:
        """Draw supplier/buyer labels in final screen space so they stay horizontal."""
        w, h = self.screen.get_size()
        for raw_pos, color, label, sublabel in (
            (self.map_config.get("supplier_pos", SUPPLIER_POS), SUPPLIER_COLOR, "SUPPLIER", f"BUY ${BUY_PRICE}"),
            (self.map_config.get("customer_pos", CUSTOMER_POS), CUSTOMER_COLOR, "BUYER", f"SELL ${SELL_PRICE}"),
        ):
            try:
                sx, sy = self._world_point_to_display(float(raw_pos[0]), float(raw_pos[1]))
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            if sx < -90 or sy < -90 or sx > w + 90 or sy > h + 90:
                continue
            title = self.small_font.render(label, True, color)
            sub = self.tiny_font.render(sublabel, True, TEXT_COLOR)
            title_rect = title.get_rect(center=(sx, sy - 52))
            sub_rect = sub.get_rect(center=(sx, sy + 52))
            for surf, rect in ((title, title_rect), (sub, sub_rect)):
                pygame.draw.rect(self.screen, (18, 21, 22), rect.inflate(8, 4), border_radius=3)
                self.screen.blit(surf, rect)

''',
)

replace_once(
    '''                    # Nameplates are screen-space UI and therefore stay horizontal
                    # at every camera angle.
                    self.draw_player_nameplates()
                    self.draw_hud()
''',
    '''                    # Nameplates and job-location labels are screen-space UI and
                    # therefore stay horizontal at every camera angle.
                    self.draw_player_nameplates()
                    self.draw_job_location_labels()
                    self.draw_hud()
''',
)

if text != original:
    PATH.write_text(text, encoding="utf-8")
    print("V090_MAP_MARKERS_PATCHED")
else:
    print("V090_MAP_MARKERS_ALREADY_PRESENT")
