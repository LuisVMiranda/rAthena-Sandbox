-- Consolidated from historical upgrade: 20260226

ALTER TABLE `ml_market_log`
  ADD INDEX IF NOT EXISTS `idx_ml_market_event_time_id` (`event_time`, `id`),
  ADD INDEX IF NOT EXISTS `idx_ml_market_item_time` (`item_id`, `event_time`),
  ADD INDEX IF NOT EXISTS `idx_ml_market_seller_account_time` (`seller_account_id`, `event_time`),
  ADD INDEX IF NOT EXISTS `idx_ml_market_buyer_account_time` (`buyer_account_id`, `event_time`);

ALTER TABLE `ml_chat_log`
  ADD INDEX IF NOT EXISTS `idx_ml_chat_event_time_id` (`event_time`, `id`),
  ADD INDEX IF NOT EXISTS `idx_ml_chat_account_time` (`account_id`, `event_time`),
  ADD INDEX IF NOT EXISTS `idx_ml_chat_char_time` (`char_id`, `event_time`),
  ADD INDEX IF NOT EXISTS `idx_ml_chat_hash_time` (`anonymized_hash`, `event_time`);

CREATE TABLE IF NOT EXISTS `ml_market_housekeeping_metrics` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `started_at` DATETIME(6) NOT NULL,
  `finished_at` DATETIME(6) NOT NULL,
  `duration_ms` BIGINT UNSIGNED NOT NULL,
  `rows_removed` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  `purge_mode` ENUM('partition_drop', 'chunked_delete') NOT NULL,
  `notes` VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `idx_ml_market_hk_started_at` (`started_at`),
  KEY `idx_ml_market_hk_purge_mode` (`purge_mode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `ml_chat_housekeeping_metrics` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `started_at` DATETIME(6) NOT NULL,
  `finished_at` DATETIME(6) NOT NULL,
  `duration_ms` BIGINT UNSIGNED NOT NULL,
  `rows_removed` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  `purge_mode` ENUM('partition_drop', 'chunked_delete') NOT NULL,
  `notes` VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `idx_ml_chat_hk_started_at` (`started_at`),
  KEY `idx_ml_chat_hk_purge_mode` (`purge_mode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE `ml_market_insights`
  ADD UNIQUE KEY IF NOT EXISTS `uk_ml_market_insights_item_window` (`item_id`, `window_start`, `window_end`);

ALTER TABLE `ml_advice_feedback`
  ADD UNIQUE KEY IF NOT EXISTS `uk_ml_advice_feedback_advice_char` (`advice_row_id`, `char_id`);

ALTER TABLE `ml_admin_challenges`
  ADD UNIQUE KEY IF NOT EXISTS `uk_ml_admin_challenges_account_type_created` (`account_id`, `challenge_type`, `created_at`);
