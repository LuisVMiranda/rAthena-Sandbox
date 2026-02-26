-- Consolidated from historical upgrades: 20260216, 20260217, 20260218, 20260219, 20260220, 20260221

CREATE TABLE IF NOT EXISTS `ml_telemetry` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `timestamp` DATETIME NOT NULL,
  `event_code` SMALLINT UNSIGNED NOT NULL,
  `char_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `guild_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `mob_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `map` VARCHAR(32) NOT NULL,
  `x` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `y` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `payload` TEXT NOT NULL,
  `processed` TINYINT(1) UNSIGNED NOT NULL DEFAULT 0,
  `claimed_at` DATETIME NULL,
  `claimed_by` VARCHAR(128) NULL,
  `processed_at` DATETIME NULL,
  `retry_count` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_ml_telemetry_processed_id` (`processed`, `id`),
  KEY `idx_ml_telemetry_event_code` (`event_code`),
  KEY `idx_ml_telemetry_claimed_at` (`claimed_at`),
  KEY `idx_ml_telemetry_timestamp` (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_telemetry`
  ADD COLUMN IF NOT EXISTS `processed` TINYINT(1) UNSIGNED NOT NULL DEFAULT 0 AFTER `id`,
  ADD COLUMN IF NOT EXISTS `claimed_at` DATETIME NULL AFTER `processed`,
  ADD COLUMN IF NOT EXISTS `claimed_by` VARCHAR(128) NULL AFTER `claimed_at`,
  ADD COLUMN IF NOT EXISTS `processed_at` DATETIME NULL AFTER `claimed_by`,
  ADD COLUMN IF NOT EXISTS `retry_count` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `processed_at`,
  ADD COLUMN IF NOT EXISTS `event_code` SMALLINT UNSIGNED NOT NULL DEFAULT 1 AFTER `timestamp`;

SET @acp_has_ml_event_type := (
  SELECT COUNT(*)
  FROM `information_schema`.`COLUMNS`
  WHERE `TABLE_SCHEMA` = DATABASE()
    AND `TABLE_NAME` = 'ml_telemetry'
    AND `COLUMN_NAME` = 'event_type'
);

SET @acp_migrate_event_type_sql := IF(
  @acp_has_ml_event_type > 0,
  "UPDATE `ml_telemetry` SET `event_code` = CASE `event_type` WHEN 'player_move' THEN 1 WHEN 'kill' THEN 2 WHEN 'death' THEN 3 WHEN 'trade' THEN 4 WHEN 'item_look' THEN 5 WHEN 'mob_spawn' THEN 100 ELSE 1 END WHERE COALESCE(`event_type`, '') <> ''",
  'SELECT 1'
);
PREPARE acp_stmt_migrate_event_type FROM @acp_migrate_event_type_sql;
EXECUTE acp_stmt_migrate_event_type;
DEALLOCATE PREPARE acp_stmt_migrate_event_type;

SET @acp_drop_event_type_sql := IF(
  @acp_has_ml_event_type > 0,
  'ALTER TABLE `ml_telemetry` DROP COLUMN `event_type`',
  'SELECT 1'
);
PREPARE acp_stmt_drop_event_type FROM @acp_drop_event_type_sql;
EXECUTE acp_stmt_drop_event_type;
DEALLOCATE PREPARE acp_stmt_drop_event_type;

ALTER TABLE `ml_telemetry`
  ALTER COLUMN `event_code` DROP DEFAULT;

ALTER TABLE `ml_telemetry`
  ADD INDEX IF NOT EXISTS `idx_ml_telemetry_processed_id` (`processed`, `id`),
  ADD INDEX IF NOT EXISTS `idx_ml_telemetry_event_code` (`event_code`),
  ADD INDEX IF NOT EXISTS `idx_ml_telemetry_claimed_at` (`claimed_at`),
  ADD INDEX IF NOT EXISTS `idx_ml_telemetry_timestamp` (`timestamp`);

CREATE TABLE IF NOT EXISTS `ml_event_types` (
  `code` SMALLINT UNSIGNED NOT NULL,
  `name` VARCHAR(64) NOT NULL,
  `description` VARCHAR(255) NOT NULL DEFAULT '',
  `enabled` TINYINT(1) UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (`code`),
  UNIQUE KEY `uk_ml_event_types_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `ml_event_types` (`code`, `name`, `description`, `enabled`) VALUES
  (1, 'Move', 'Player movement sample', 1),
  (2, 'Kill', 'Kill event telemetry', 1),
  (3, 'Death', 'Death event telemetry', 1),
  (4, 'Trade', 'Trade event telemetry', 1),
  (5, 'Item_Look', 'Item inspection event telemetry', 1),
  (6, 'Storage', 'Storage interaction telemetry', 1),
  (100, 'Mob_Spawn', 'Mob spawn sample', 1)
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `description` = VALUES(`description`),
  `enabled` = VALUES(`enabled`);

CREATE TABLE IF NOT EXISTS `ml_advice` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `advice_id` VARCHAR(64) NOT NULL,
  `char_id` INT UNSIGNED NOT NULL,
  `advice_text` TEXT NOT NULL,
  `bucket` INT UNSIGNED NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` DATETIME NOT NULL,
  `delivered_at` DATETIME NULL,
  `consumed_at` DATETIME NULL,
  `state` ENUM('new','delivered','consumed','expired') NOT NULL DEFAULT 'new',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ml_advice_char_advice_bucket` (`char_id`, `advice_id`, `bucket`),
  KEY `idx_ml_advice_char_state_expiry` (`char_id`, `state`, `expires_at`),
  KEY `idx_ml_advice_advice_state` (`advice_id`, `state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_advice`
  ADD COLUMN IF NOT EXISTS `advice_id` VARCHAR(64) NOT NULL AFTER `id`,
  ADD COLUMN IF NOT EXISTS `char_id` INT UNSIGNED NOT NULL AFTER `advice_id`,
  ADD COLUMN IF NOT EXISTS `bucket` INT UNSIGNED NOT NULL AFTER `advice_text`,
  ADD COLUMN IF NOT EXISTS `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER `bucket`,
  ADD COLUMN IF NOT EXISTS `expires_at` DATETIME NOT NULL AFTER `created_at`,
  ADD COLUMN IF NOT EXISTS `delivered_at` DATETIME NULL AFTER `expires_at`,
  ADD COLUMN IF NOT EXISTS `consumed_at` DATETIME NULL AFTER `delivered_at`,
  ADD COLUMN IF NOT EXISTS `state` ENUM('new','delivered','consumed','expired') NOT NULL DEFAULT 'new' AFTER `consumed_at`;

UPDATE `ml_advice`
SET `state` = 'expired'
WHERE `state` IN ('new', 'delivered')
  AND `expires_at` <= NOW();

ALTER TABLE `ml_advice`
  ADD UNIQUE KEY IF NOT EXISTS `uk_ml_advice_char_advice_bucket` (`char_id`, `advice_id`, `bucket`),
  ADD KEY IF NOT EXISTS `idx_ml_advice_char_state_expiry` (`char_id`, `state`, `expires_at`),
  ADD KEY IF NOT EXISTS `idx_ml_advice_advice_state` (`advice_id`, `state`);

CREATE TABLE IF NOT EXISTS `ml_admin_flags` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL,
  `flagged_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `reason` VARCHAR(128) NOT NULL,
  `window_minutes` SMALLINT UNSIGNED NOT NULL,
  `window_start` DATETIME NOT NULL,
  `window_end` DATETIME NOT NULL,
  `evidence_event_count` INT UNSIGNED NOT NULL DEFAULT 0,
  `raw_anomaly_score` DOUBLE NOT NULL,
  `calibrated_confidence` DOUBLE NOT NULL,
  `top_contributing_features` JSON NULL,
  `details` JSON NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ml_admin_flags_account_time` (`account_id`, `flagged_at`),
  KEY `idx_ml_admin_flags_confidence` (`calibrated_confidence`),
  KEY `idx_ml_admin_flags_reason` (`reason`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_admin_flags`
  ADD COLUMN IF NOT EXISTS `window_minutes` SMALLINT UNSIGNED NOT NULL DEFAULT 5 AFTER `reason`,
  ADD COLUMN IF NOT EXISTS `window_start` DATETIME NULL AFTER `window_minutes`,
  ADD COLUMN IF NOT EXISTS `window_end` DATETIME NULL AFTER `window_start`,
  ADD COLUMN IF NOT EXISTS `evidence_event_count` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `window_end`,
  ADD COLUMN IF NOT EXISTS `raw_anomaly_score` DOUBLE NULL AFTER `evidence_event_count`,
  ADD COLUMN IF NOT EXISTS `calibrated_confidence` DOUBLE NULL AFTER `raw_anomaly_score`,
  ADD COLUMN IF NOT EXISTS `top_contributing_features` JSON NULL AFTER `calibrated_confidence`,
  ADD COLUMN IF NOT EXISTS `details` JSON NULL AFTER `top_contributing_features`;

ALTER TABLE `ml_admin_flags`
  ADD KEY IF NOT EXISTS `idx_ml_admin_flags_account_time` (`account_id`, `flagged_at`),
  ADD KEY IF NOT EXISTS `idx_ml_admin_flags_confidence` (`calibrated_confidence`),
  ADD KEY IF NOT EXISTS `idx_ml_admin_flags_reason` (`reason`);

CREATE TABLE IF NOT EXISTS `ml_telemetry_housekeeping_metrics` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `started_at` DATETIME(6) NOT NULL,
  `finished_at` DATETIME(6) NOT NULL,
  `duration_ms` BIGINT UNSIGNED NOT NULL,
  `rows_removed` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  `purge_mode` ENUM('partition_drop', 'chunked_delete') NOT NULL,
  `notes` VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `idx_ml_tel_hk_started_at` (`started_at`),
  KEY `idx_ml_tel_hk_purge_mode` (`purge_mode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
