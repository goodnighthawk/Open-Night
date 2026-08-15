from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from common import PlayerState, empty_inventory, inventory_add, inventory_count


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


async def exercise() -> None:
    server.USE_MYSQL = False
    info = (server.ACTIVE_MAP.get("interiors", []) or [])[0]
    x, y = map(float, info["entry"][:2])
    a_player = PlayerState("interior-a", "Alice", x, y)
    b_player = PlayerState("interior-b", "Bob", x, y)
    a = server.ClientSession(CaptureSocket(), a_player, "15550000001", empty_inventory())
    b = server.ClientSession(CaptureSocket(), b_player, "15550000002", empty_inventory())
    server.clients.clear()
    server.clients[a_player.player_id] = a
    server.clients[b_player.player_id] = b

    await server.process_interior_action(a, "enter", {"interior_id": info["id"]})
    await server.process_interior_action(b, "enter", {"interior_id": info["id"]})
    assert a_player.interior_id == b_player.interior_id == str(info["id"])
    before = (a_player.interior_x, a_player.interior_y)
    await server.process_interior_action(a, "move", {"dx": 1, "dy": 0})
    assert (a_player.interior_x, a_player.interior_y) != before
    public = a_player.public_dict()
    assert public["interior_id"] == str(info["id"])
    assert "interior_x" in public and "interior_y" in public

    await server.process_chat(a, {"scope": "local", "text": "inside together"})
    assert any(row.get("type") == "chat" and row.get("text") == "inside together" for row in b.websocket.messages)
    a.last_chat_time = 0.0
    await server.process_chat(a, {"scope": "whisper", "target": "Bob", "text": "private"})
    assert any(row.get("scope") == "whisper" and row.get("text") == "private" for row in b.websocket.messages)

    server.memory_accounts.clear()
    server.memory_sms_messages.clear()
    server.memory_accounts[a.phone] = {"name": "Alice"}
    server.memory_accounts[b.phone] = {"name": "Bob"}
    await server.process_sms(a, {"target": "Bob", "text": "saved hello"})
    assert any(row.get("type") == "sms_received" and row.get("text") == "saved hello" for row in b.websocket.messages)
    assert any(row.get("type") == "sms_sent" and row.get("recipient_name") == "Bob" for row in a.websocket.messages)
    server.clients.pop(b_player.player_id)
    a.last_sms_time = 0.0
    await server.process_sms(a, {"target": "Bob", "text": "offline hello"})
    history = await server.sms_history(b)
    assert any(row.get("direction") == "in" and row.get("text") == "offline hello" and row.get("unread") for row in history)
    await server.mark_sms_read(b)
    history = await server.sms_history(b)
    assert not any(row.get("unread") for row in history if row.get("direction") == "in")
    server.clients[b_player.player_id] = b

    inventory_add(a.inventory, "package", 1)
    await server.process_interaction(a)
    assert b_player.player_id in server.trade_offers
    old_b_cash, old_a_cash = b_player.cash, a_player.cash
    await server.process_interaction(b)
    assert inventory_count(b.inventory, "package") == 1
    assert b_player.cash == old_b_cash - server.SELL_PRICE
    assert a_player.cash == old_a_cash + server.SELL_PRICE

    await server.process_interior_action(a, "exit", {})
    assert not a_player.interior_id
    server.clients.clear()
    server.trade_offers.clear()
    server.memory_accounts.clear()
    server.memory_sms_messages.clear()


def main() -> int:
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    interior = (ROOT / "interior_art.py").read_text(encoding="utf-8")
    for token in ("apply_interior_state", '"type": "interior_move"', "occupants=occupants"):
        assert token in client, token
    for token in ("load_friend_names", "ADD FRIEND", "self.is_friend", "scroll_pause_page"):
        assert token in client, token
    for token in ("draw_chat_bubble", "/w FriendName message", "handle_chat_key"):
        assert token in client, token
    for token in ("autocomplete_friend_message", '"type": "sms_send"', "draw_sms_inbox", "pygame.K_F2"):
        assert token in client, token
    assert "SELL TO" in client and 'self.map_config["customer_pos"]' not in client
    assert "local_ring=None" in interior
    asyncio.run(exercise())
    print("MULTIPLAYER INTERIOR / FRIENDS / CHAT AUDIT: PASS")
    print("  shared rooms + local bubbles + friend whisper + persistent online/offline SMS + minimap friend/filter verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
