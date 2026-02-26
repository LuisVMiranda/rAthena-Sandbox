-- Watch Center (MVP): case-based monitoring + change events

CREATE TABLE IF NOT EXISTS `acp_watch_cases` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_by` VARCHAR(191) NOT NULL DEFAULT '',
  `watch_type` VARCHAR(16) NOT NULL,
  `char_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `account_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `nameid` INT UNSIGNED NOT NULL DEFAULT 0,
  `label` VARCHAR(191) NOT NULL DEFAULT '',
  `check_every_seconds` INT UNSIGNED NOT NULL DEFAULT 300,
  `severity` VARCHAR(16) NOT NULL DEFAULT 'medium',
  `notify_discord` TINYINT(1) NOT NULL DEFAULT 1,
  `notify_telegram` TINYINT(1) NOT NULL DEFAULT 1,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `notes` TEXT NULL,
  `last_snapshot` LONGTEXT NULL,
  `last_checked_at` DATETIME NULL,
  `last_notified_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  KEY `idx_acp_watch_cases_enabled_checked` (`enabled`, `last_checked_at`),
  KEY `idx_acp_watch_cases_type` (`watch_type`),
  KEY `idx_acp_watch_cases_char` (`char_id`),
  KEY `idx_acp_watch_cases_account` (`account_id`),
  KEY `idx_acp_watch_cases_item` (`nameid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `acp_watch_events` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `case_id` BIGINT UNSIGNED NOT NULL,
  `event_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `event_type` VARCHAR(64) NOT NULL DEFAULT 'change_detected',
  `severity` VARCHAR(16) NOT NULL DEFAULT 'medium',
  `summary` VARCHAR(255) NOT NULL DEFAULT '',
  `details_json` LONGTEXT NULL,
  `notified_discord` TINYINT(1) NOT NULL DEFAULT 0,
  `notified_telegram` TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_acp_watch_events_case_time` (`case_id`, `event_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
