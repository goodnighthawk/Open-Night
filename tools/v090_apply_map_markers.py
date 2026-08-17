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

world_anchor = '''        for pid, marker in self.map_players.items():
'''
world_markers = '''        # Job-economy locations are client-side map UI, not baked map text. This
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

if text != original:
    PATH.write_text(text, encoding="utf-8")
    print("V090_MAP_MARKERS_PATCHED")
else:
    print("V090_MAP_MARKERS_ALREADY_PRESENT")
