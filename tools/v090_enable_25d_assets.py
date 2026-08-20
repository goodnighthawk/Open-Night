from pathlib import Path

path = Path('environment_art.py')
text = path.read_text(encoding='utf-8')
old = '''        # Deterministically seed a subset of larger roofs with the converted
        # user-authored voxel building. It behaves as a 2.5D rooftop tower and
        # remains baked into the same rotated chunk surface as other geometry.
        if elevated_25d and index % 13 == 0 and inner.width >= 72 and inner.height >= 62:
            imported = _open_asset_building("isometric", min(92, max(48, inner.height - 8)))
            if imported is not None:
                anchor = imported.get_rect(midbottom=(inner.centerx, inner.bottom - 3))
                pygame.draw.ellipse(surface, BUILDING_SHADOW_COLOR, anchor.inflate(8, -max(1, anchor.height // 2)).move(5, max(3, anchor.height // 3)))
                surface.blit(imported, anchor)
'''
new = '''        # v0.9: the approved 2.5D city import is a visible runtime art layer,
        # not a rare easter egg. Use it on a deterministic quarter of qualifying
        # larger roofs so normal traversal actually exposes the imported pack
        # while keeping enough procedural variety to avoid obvious repetition.
        if elevated_25d and index % 4 == 0 and inner.width >= 72 and inner.height >= 62:
            imported = _open_asset_building("isometric", min(104, max(52, inner.height - 6)))
            if imported is not None:
                anchor = imported.get_rect(midbottom=(inner.centerx, inner.bottom - 3))
                pygame.draw.ellipse(surface, BUILDING_SHADOW_COLOR, anchor.inflate(8, -max(1, anchor.height // 2)).move(5, max(3, anchor.height // 3)))
                surface.blit(imported, anchor)
'''
if new in text:
    print('v0.9 2.5D asset promotion already applied')
    raise SystemExit(0)
if old not in text:
    raise SystemExit('expected 2.5D roof-module block not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('v0.9 2.5D asset promotion applied')
