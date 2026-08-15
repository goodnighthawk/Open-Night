from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from common import CHARACTER_DEFAULT, STARTING_CASH, empty_inventory, normalize_character, normalize_inventory


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    database: str = "pymmo"
    user: str = "root"
    password: str = ""


class InventoryDatabase:
    """Small synchronous MySQL repository.

    Server code calls these methods with asyncio.to_thread(), keeping blocking
    database I/O off the game server event loop.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        if not re.fullmatch(r"[A-Za-z0-9_]+", config.database):
            raise ValueError("Database name may contain only letters, numbers, and underscores.")

    def _connect(self, include_database: bool = True):
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "autocommit": False,
            "connection_timeout": 5,
        }
        if include_database:
            kwargs["database"] = self.config.database
        try:
            import mysql.connector
        except ImportError as exc:
            raise RuntimeError("mysql-connector-python is not installed. Run: python -m pip install -r requirements.txt") from exc
        return mysql.connector.connect(**kwargs)


    def status(self) -> dict:
        """Return lightweight launcher health information without mutating schema."""
        result = {
            "online": False,
            "schema_ready": False,
            "account_count": None,
            "server_version": None,
        }
        conn = self._connect(include_database=False)
        try:
            cur = conn.cursor()
            cur.execute("SELECT VERSION()")
            row = cur.fetchone()
            result["server_version"] = str(row[0]) if row else None
            result["online"] = True
            cur.close()
        finally:
            conn.close()

        try:
            conn = self._connect(include_database=True)
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM player_accounts")
                row = cur.fetchone()
                result["account_count"] = int(row[0]) if row else 0
                result["schema_ready"] = True
                cur.close()
            finally:
                conn.close()
        except Exception as exc:
            # Missing database/table means MySQL itself is online but the schema
            # hasn't been initialized yet. Authentication/connection failures
            # here are re-raised so the launcher doesn't report a false ONLINE.
            errno = getattr(exc, "errno", None)
            if errno not in (1049, 1146):
                raise
        return result

    def initialize(self) -> None:
        # The configured user must have CREATE DATABASE permission for first run,
        # or the database can be created manually ahead of time.
        conn = self._connect(include_database=False)
        try:
            cur = conn.cursor()
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

        conn = self._connect(include_database=True)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS player_accounts (
                    phone VARCHAR(20) PRIMARY KEY,
                    display_name VARCHAR(32) NOT NULL,
                    cash INT NOT NULL DEFAULT 200,
                    skin_tone TINYINT UNSIGNED NOT NULL DEFAULT 2,
                    hair_style TINYINT UNSIGNED NOT NULL DEFAULT 1,
                    hair_color TINYINT UNSIGNED NOT NULL DEFAULT 1,
                    top_color TINYINT UNSIGNED NOT NULL DEFAULT 2,
                    pants_color TINYINT UNSIGNED NOT NULL DEFAULT 0,
                    character_profile VARCHAR(48) NOT NULL DEFAULT 'tshirt_blue_curly',
                    character_body VARCHAR(48) NOT NULL DEFAULT 'neutral_body',
                    character_head VARCHAR(48) NOT NULL DEFAULT 'curly_short',
                    character_top VARCHAR(48) NOT NULL DEFAULT 'tshirt_blue',
                    character_bottom VARCHAR(48) NOT NULL DEFAULT 'dark_jeans',
                    character_footwear VARCHAR(48) NOT NULL DEFAULT 'black_sneakers',
                    character_accessory VARCHAR(48) NOT NULL DEFAULT 'none',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            # Migrate legacy databases without requiring the
            # user to drop account data. SHOW COLUMNS works on older MySQL 8
            # installations where ADD COLUMN IF NOT EXISTS support can vary.
            cur.execute("SHOW COLUMNS FROM player_accounts")
            existing_columns = {str(row[0]) for row in cur.fetchall()}
            character_columns = {
                "skin_tone": "TINYINT UNSIGNED NOT NULL DEFAULT 2",
                "hair_style": "TINYINT UNSIGNED NOT NULL DEFAULT 1",
                "hair_color": "TINYINT UNSIGNED NOT NULL DEFAULT 1",
                "top_color": "TINYINT UNSIGNED NOT NULL DEFAULT 2",
                "pants_color": "TINYINT UNSIGNED NOT NULL DEFAULT 0",
                "character_profile": "VARCHAR(48) NOT NULL DEFAULT 'tshirt_blue_curly'",
                "character_body": "VARCHAR(48) NOT NULL DEFAULT 'neutral_body'",
                "character_head": "VARCHAR(48) NOT NULL DEFAULT 'curly_short'",
                "character_top": "VARCHAR(48) NOT NULL DEFAULT 'tshirt_blue'",
                "character_bottom": "VARCHAR(48) NOT NULL DEFAULT 'dark_jeans'",
                "character_footwear": "VARCHAR(48) NOT NULL DEFAULT 'black_sneakers'",
                "character_accessory": "VARCHAR(48) NOT NULL DEFAULT 'none'",
            }
            for column, definition in character_columns.items():
                if column not in existing_columns:
                    cur.execute(f"ALTER TABLE player_accounts ADD COLUMN `{column}` {definition}")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_slots (
                    phone VARCHAR(20) NOT NULL,
                    slot_index SMALLINT UNSIGNED NOT NULL,
                    item_id VARCHAR(64) NOT NULL,
                    quantity INT UNSIGNED NOT NULL,
                    PRIMARY KEY (phone, slot_index),
                    CONSTRAINT fk_inventory_phone FOREIGN KEY (phone)
                        REFERENCES player_accounts(phone) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS open_night_deployment (
                    setting_key VARCHAR(64) PRIMARY KEY,
                    setting_value VARCHAR(128) NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def reset_for_patch(self, patch_id: str) -> bool:
        """Clear prototype persistence once when the deployed patch ID changes."""
        clean_patch = str(patch_id).strip()
        if not clean_patch or len(clean_patch) > 128:
            raise ValueError("Patch ID must contain 1 to 128 characters.")
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT setting_value FROM open_night_deployment "
                "WHERE setting_key='persistence_patch_id' FOR UPDATE"
            )
            row = cur.fetchone()
            previous = str(row[0]) if row else None
            if previous == clean_patch:
                conn.commit();cur.close();return False
            # Child rows are removed first for compatibility with the explicit
            # foreign key, even though account deletion also cascades.
            cur.execute("DELETE FROM inventory_slots")
            cur.execute("DELETE FROM player_accounts")
            cur.execute(
                "INSERT INTO open_night_deployment (setting_key, setting_value) "
                "VALUES ('persistence_patch_id', %s) "
                "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
                (clean_patch,),
            )
            conn.commit();cur.close();return True
        except Exception:
            conn.rollback();raise
        finally:
            conn.close()

    def load_or_create_account(self, phone: str, display_name: str, requested_appearance: dict | None = None) -> tuple[int, list[dict | None], dict, bool]:
        conn = self._connect()
        created = False
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("""SELECT cash, display_name, skin_tone, hair_style, hair_color, top_color, pants_color,
                character_profile, character_body, character_head, character_top, character_bottom,
                character_footwear, character_accessory FROM player_accounts WHERE phone=%s FOR UPDATE""", (phone,))
            row = cur.fetchone()
            requested = normalize_character(requested_appearance) if requested_appearance is not None else None
            if row is None:
                appearance = requested or dict(CHARACTER_DEFAULT)
                cur.execute(
                    """INSERT INTO player_accounts
                    (phone, display_name, cash, skin_tone, hair_style, hair_color, top_color, pants_color,
                     character_profile, character_body, character_head, character_top, character_bottom,
                     character_footwear, character_accessory)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (phone, display_name, STARTING_CASH, appearance["skin_tone"], appearance["hair_style"],
                     appearance["hair_color"], appearance["top_color"], appearance["pants_color"],
                     appearance["profile"], appearance["body"], appearance["head"], appearance["top"],
                     appearance["bottom"], appearance["footwear"], appearance["accessory"]),
                )
                cash = STARTING_CASH
                created = True
            else:
                cash = int(row["cash"])
                stored = normalize_character({
                    "skin_tone": row.get("skin_tone"), "hair_style": row.get("hair_style"),
                    "hair_color": row.get("hair_color"), "top_color": row.get("top_color"),
                    "pants_color": row.get("pants_color"), "profile": row.get("character_profile"),
                    "body": row.get("character_body"), "head": row.get("character_head"),
                    "top": row.get("character_top"), "bottom": row.get("character_bottom"),
                    "footwear": row.get("character_footwear"), "accessory": row.get("character_accessory"),
                })
                appearance = requested or stored
                # Login can update the prototype display name. Appearance changes
                # only when the launcher explicitly sends a customized profile.
                cur.execute(
                    """UPDATE player_accounts SET display_name=%s, skin_tone=%s, hair_style=%s,
                    hair_color=%s, top_color=%s, pants_color=%s, character_profile=%s, character_body=%s,
                    character_head=%s, character_top=%s, character_bottom=%s, character_footwear=%s,
                    character_accessory=%s WHERE phone=%s""",
                    (display_name, appearance["skin_tone"], appearance["hair_style"], appearance["hair_color"],
                     appearance["top_color"], appearance["pants_color"], appearance["profile"], appearance["body"],
                     appearance["head"], appearance["top"], appearance["bottom"], appearance["footwear"],
                     appearance["accessory"], phone),
                )

            cur.execute(
                "SELECT slot_index, item_id, quantity FROM inventory_slots WHERE phone=%s ORDER BY slot_index",
                (phone,),
            )
            slots = empty_inventory()
            for item in cur.fetchall():
                index = int(item["slot_index"])
                if 0 <= index < len(slots):
                    slots[index] = {"item_id": str(item["item_id"]), "quantity": int(item["quantity"])}
            conn.commit()
            return cash, normalize_inventory(slots), normalize_character(appearance), created
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_player_state(self, phone: str, display_name: str, cash: int, slots: list[dict | None], appearance: dict | None = None) -> None:
        clean = normalize_inventory(slots)
        character = normalize_character(appearance)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE player_accounts SET display_name=%s, cash=%s, skin_tone=%s, hair_style=%s,
                hair_color=%s, top_color=%s, pants_color=%s, character_profile=%s, character_body=%s,
                character_head=%s, character_top=%s, character_bottom=%s, character_footwear=%s,
                character_accessory=%s WHERE phone=%s""",
                (display_name, int(cash), character["skin_tone"], character["hair_style"],
                 character["hair_color"], character["top_color"], character["pants_color"], character["profile"],
                 character["body"], character["head"], character["top"], character["bottom"],
                 character["footwear"], character["accessory"], phone),
            )
            cur.execute("DELETE FROM inventory_slots WHERE phone=%s", (phone,))
            rows = [
                (phone, index, slot["item_id"], int(slot["quantity"]))
                for index, slot in enumerate(clean)
                if slot is not None
            ]
            if rows:
                cur.executemany(
                    "INSERT INTO inventory_slots (phone, slot_index, item_id, quantity) VALUES (%s, %s, %s, %s)",
                    rows,
                )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def mysql_error_text(exc: BaseException) -> str:
    errno = getattr(exc, "errno", None)
    if errno is not None:
        return f"MySQL error {errno}: {exc}"
    return str(exc)
