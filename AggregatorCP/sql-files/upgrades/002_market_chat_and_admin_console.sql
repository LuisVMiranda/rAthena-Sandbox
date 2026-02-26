-- Consolidated from historical upgrades: 20260222, 20260223, 20260224, 20260225_admin_console

CREATE TABLE IF NOT EXISTS `ml_market_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `event_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `item_id` INT UNSIGNED NOT NULL,
  `price` INT UNSIGNED NOT NULL,
  `quantity` INT UNSIGNED NOT NULL,
  `seller_char_id` INT UNSIGNED NULL,
  `seller_account_id` INT UNSIGNED NULL,
  `buyer_char_id` INT UNSIGNED NULL,
  `buyer_account_id` INT UNSIGNED NULL,
  `map` VARCHAR(32) NOT NULL,
  `source_type` VARCHAR(32) NOT NULL,
  `metadata_json` JSON NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ml_market_time` (`event_time`),
  KEY `idx_ml_market_item_time` (`item_id`, `event_time`),
  KEY `idx_ml_market_seller_account_time` (`seller_account_id`, `event_time`),
  KEY `idx_ml_market_buyer_account_time` (`buyer_account_id`, `event_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `ml_chat_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `event_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `char_id` INT UNSIGNED NULL,
  `account_id` INT UNSIGNED NULL,
  `anonymized_hash` CHAR(32) NOT NULL,
  `channel_type` VARCHAR(24) NOT NULL,
  `map` VARCHAR(32) NOT NULL,
  `metadata_json` JSON NULL,
  PRIMARY KEY (`id`),
  KEY `idx_ml_chat_time` (`event_time`),
  KEY `idx_ml_chat_account_time` (`account_id`, `event_time`),
  KEY `idx_ml_chat_char_time` (`char_id`, `event_time`),
  KEY `idx_ml_chat_hash_time` (`anonymized_hash`, `event_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `ml_advice_feedback` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `advice_row_id` BIGINT UNSIGNED NOT NULL,
  `char_id` INT UNSIGNED NOT NULL,
  `feedback_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `helpful` TINYINT(1) NOT NULL,
  `context` VARCHAR(255) NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ml_advice_feedback_row_player_time` (`advice_row_id`, `char_id`, `feedback_at`),
  KEY `idx_ml_advice_feedback_char_time` (`char_id`, `feedback_at`),
  KEY `idx_ml_advice_feedback_helpful_time` (`helpful`, `feedback_at`),
  CONSTRAINT `fk_ml_advice_feedback_advice_row`
    FOREIGN KEY (`advice_row_id`) REFERENCES `ml_advice` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_advice_feedback`
  ADD COLUMN IF NOT EXISTS `advice_row_id` BIGINT UNSIGNED NOT NULL AFTER `id`,
  ADD COLUMN IF NOT EXISTS `char_id` INT UNSIGNED NOT NULL AFTER `advice_row_id`,
  ADD COLUMN IF NOT EXISTS `feedback_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) AFTER `char_id`,
  ADD COLUMN IF NOT EXISTS `helpful` TINYINT(1) NOT NULL AFTER `feedback_at`,
  ADD COLUMN IF NOT EXISTS `context` VARCHAR(255) NULL AFTER `helpful`;

ALTER TABLE `ml_advice_feedback`
  ADD UNIQUE KEY IF NOT EXISTS `uk_ml_advice_feedback_row_player_time` (`advice_row_id`, `char_id`, `feedback_at`),
  ADD KEY IF NOT EXISTS `idx_ml_advice_feedback_char_time` (`char_id`, `feedback_at`),
  ADD KEY IF NOT EXISTS `idx_ml_advice_feedback_helpful_time` (`helpful`, `feedback_at`);

CREATE TABLE IF NOT EXISTS `ml_market_insights` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `item_id` INT UNSIGNED NOT NULL,
  `insight_time` DATETIME(6) NOT NULL,
  `window_start` DATETIME(6) NOT NULL,
  `window_end` DATETIME(6) NOT NULL,
  `actual_price` INT UNSIGNED NOT NULL,
  `expected_price` DECIMAL(14,4) NOT NULL,
  `deviation_ratio` DECIMAL(10,6) NOT NULL,
  `classification` ENUM('undervalued', 'inflation_spike', 'normal') NOT NULL,
  `confidence` DECIMAL(6,5) NOT NULL,
  `window_points` INT UNSIGNED NOT NULL,
  `window_minutes` INT UNSIGNED NOT NULL,
  `metadata_json` JSON NULL,
  `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ml_market_insights_item_window` (`item_id`, `window_start`, `window_end`),
  KEY `idx_ml_market_insights_class_time` (`classification`, `insight_time`),
  KEY `idx_ml_market_insights_item_time` (`item_id`, `insight_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_market_insights`
  ADD COLUMN IF NOT EXISTS `item_id` INT UNSIGNED NOT NULL AFTER `id`,
  ADD COLUMN IF NOT EXISTS `insight_time` DATETIME(6) NOT NULL AFTER `item_id`,
  ADD COLUMN IF NOT EXISTS `window_start` DATETIME(6) NOT NULL AFTER `insight_time`,
  ADD COLUMN IF NOT EXISTS `window_end` DATETIME(6) NOT NULL AFTER `window_start`,
  ADD COLUMN IF NOT EXISTS `actual_price` INT UNSIGNED NOT NULL AFTER `window_end`,
  ADD COLUMN IF NOT EXISTS `expected_price` DECIMAL(14,4) NOT NULL AFTER `actual_price`,
  ADD COLUMN IF NOT EXISTS `deviation_ratio` DECIMAL(10,6) NOT NULL AFTER `expected_price`,
  ADD COLUMN IF NOT EXISTS `classification` ENUM('undervalued', 'inflation_spike', 'normal') NOT NULL AFTER `deviation_ratio`,
  ADD COLUMN IF NOT EXISTS `confidence` DECIMAL(6,5) NOT NULL AFTER `classification`,
  ADD COLUMN IF NOT EXISTS `window_points` INT UNSIGNED NOT NULL AFTER `confidence`,
  ADD COLUMN IF NOT EXISTS `window_minutes` INT UNSIGNED NOT NULL AFTER `window_points`,
  ADD COLUMN IF NOT EXISTS `metadata_json` JSON NULL AFTER `window_minutes`,
  ADD COLUMN IF NOT EXISTS `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) AFTER `metadata_json`;

ALTER TABLE `ml_market_insights`
  ADD UNIQUE KEY IF NOT EXISTS `uk_ml_market_insights_item_window` (`item_id`, `window_start`, `window_end`),
  ADD KEY IF NOT EXISTS `idx_ml_market_insights_class_time` (`classification`, `insight_time`),
  ADD KEY IF NOT EXISTS `idx_ml_market_insights_item_time` (`item_id`, `insight_time`);



CREATE TABLE IF NOT EXISTS `ml_challenges` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL,
  `char_id` INT UNSIGNED NOT NULL,
  `suspect_score` INT NOT NULL DEFAULT 0,
  `target_map` VARCHAR(32) NOT NULL,
  `target_x` SMALLINT NOT NULL,
  `target_y` SMALLINT NOT NULL,
  `deadline` DATETIME NOT NULL,
  `challenge_state` ENUM('pending','active','completed','failed','timed_out') NOT NULL DEFAULT 'pending',
  `result` ENUM('success','failed','timeout') NULL,
  `bot_confirmed` TINYINT(1) NOT NULL DEFAULT 0,
  `issued_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ml_challenges_state_issued` (`challenge_state`, `issued_at`),
  KEY `idx_ml_challenges_char_state` (`char_id`, `challenge_state`),
  KEY `idx_ml_challenges_deadline` (`deadline`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_challenges`
  ADD COLUMN IF NOT EXISTS `account_id` INT UNSIGNED NOT NULL AFTER `id`,
  ADD COLUMN IF NOT EXISTS `char_id` INT UNSIGNED NOT NULL AFTER `account_id`,
  ADD COLUMN IF NOT EXISTS `suspect_score` INT NOT NULL DEFAULT 0 AFTER `char_id`,
  ADD COLUMN IF NOT EXISTS `target_map` VARCHAR(32) NOT NULL AFTER `suspect_score`,
  ADD COLUMN IF NOT EXISTS `target_x` SMALLINT NOT NULL AFTER `target_map`,
  ADD COLUMN IF NOT EXISTS `target_y` SMALLINT NOT NULL AFTER `target_x`,
  ADD COLUMN IF NOT EXISTS `deadline` DATETIME NOT NULL AFTER `target_y`,
  ADD COLUMN IF NOT EXISTS `challenge_state` ENUM('pending','active','completed','failed','timed_out') NOT NULL DEFAULT 'pending' AFTER `deadline`,
  ADD COLUMN IF NOT EXISTS `result` ENUM('success','failed','timeout') NULL AFTER `challenge_state`,
  ADD COLUMN IF NOT EXISTS `bot_confirmed` TINYINT(1) NOT NULL DEFAULT 0 AFTER `result`,
  ADD COLUMN IF NOT EXISTS `issued_at` DATETIME NULL AFTER `bot_confirmed`,
  ADD COLUMN IF NOT EXISTS `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER `issued_at`;

ALTER TABLE `ml_challenges`
  ADD KEY IF NOT EXISTS `idx_ml_challenges_state_issued` (`challenge_state`, `issued_at`),
  ADD KEY IF NOT EXISTS `idx_ml_challenges_char_state` (`char_id`, `challenge_state`),
  ADD KEY IF NOT EXISTS `idx_ml_challenges_deadline` (`deadline`);

CREATE TABLE IF NOT EXISTS `ml_admin_challenges` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `account_id` INT UNSIGNED NOT NULL,
  `challenge_type` VARCHAR(64) NOT NULL,
  `challenge_score` DECIMAL(10,2) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ml_admin_challenges_account_created` (`account_id`, `created_at`)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `ml_admin_action_audit` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `action_id` CHAR(36) NOT NULL,
  `admin_user` VARCHAR(64) NOT NULL,
  `gm_command` VARCHAR(16) NOT NULL,
  `target_char_id` INT UNSIGNED NOT NULL,
  `reason` VARCHAR(250) NOT NULL,
  `status` ENUM('requested','queued','dispatched','failed','rejected') NOT NULL,
  `outcome_message` VARCHAR(500) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ml_admin_action_audit_action` (`action_id`),
  KEY `idx_ml_admin_action_audit_created` (`created_at`)
) ENGINE=InnoDB;
