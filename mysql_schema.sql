-- Optional manual schema setup for Python MMO v2.2.
-- server.py / server_launcher.py can create and migrate this schema automatically.

CREATE DATABASE IF NOT EXISTS pymmo
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE pymmo;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- If upgrading an older database, use the graphical server launcher's
-- CREATE / REPAIR SCHEMA button instead of manually running ALTER statements.

CREATE TABLE IF NOT EXISTS inventory_slots (
    phone VARCHAR(20) NOT NULL,
    slot_index SMALLINT UNSIGNED NOT NULL,
    item_id VARCHAR(64) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (phone, slot_index),
    CONSTRAINT fk_inventory_phone FOREIGN KEY (phone)
        REFERENCES player_accounts(phone) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
