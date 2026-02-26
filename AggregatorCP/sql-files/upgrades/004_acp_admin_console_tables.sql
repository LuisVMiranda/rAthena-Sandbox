-- AggregatorCP admin/player-control tables using acp_ prefix
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS `acp_admin_decisions` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `char_id` INT UNSIGNED NOT NULL,
  `account_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `decision` VARCHAR(64) NOT NULL,
  `reason` VARCHAR(255) NULL,
  `reason_mode` VARCHAR(16) NOT NULL DEFAULT 'log',
  `duration_value` INT UNSIGNED NOT NULL DEFAULT 0,
  `duration_unit` VARCHAR(16) NOT NULL DEFAULT 'none',
  PRIMARY KEY (`id`),
  KEY `idx_acp_admin_decisions_created` (`created_at`),
  KEY `idx_acp_admin_decisions_char` (`char_id`),
  KEY `idx_acp_admin_decisions_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `acp_admin_action_queue` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `action_id` VARCHAR(64) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `char_id` INT UNSIGNED NOT NULL,
  `account_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `decision` VARCHAR(32) NOT NULL,
  `reason` VARCHAR(255) NULL,
  `reason_mode` VARCHAR(16) NOT NULL DEFAULT 'log',
  `duration_value` INT UNSIGNED NOT NULL DEFAULT 0,
  `duration_unit` VARCHAR(16) NOT NULL DEFAULT 'none',
  `status` VARCHAR(32) NOT NULL DEFAULT 'queued',
  `bridge_message` TEXT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_acp_admin_action_queue_action` (`action_id`),
  KEY `idx_acp_admin_action_queue_status_created` (`status`, `created_at`),
  KEY `idx_acp_admin_action_queue_char` (`char_id`),
  KEY `idx_acp_admin_action_queue_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `acp_gm_command_queue` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `action_id` VARCHAR(64) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `gm_command` VARCHAR(24) NOT NULL,
  `target_char_id` INT UNSIGNED NOT NULL,
  `reason` VARCHAR(255) NULL,
  `reason_mode` VARCHAR(16) NOT NULL DEFAULT 'log',
  `duration_value` INT UNSIGNED NOT NULL DEFAULT 0,
  `duration_unit` VARCHAR(16) NOT NULL DEFAULT 'none',
  `requested_by` VARCHAR(64) NULL,
  `status` VARCHAR(24) NOT NULL DEFAULT 'pending',
  `attempts` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `last_error` TEXT NULL,
  `applied_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_acp_gm_command_queue_action` (`action_id`),
  KEY `idx_acp_gm_command_queue_status_created` (`status`, `created_at`),
  KEY `idx_acp_gm_command_queue_target` (`target_char_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Requeue stale processing rows after deployments/restarts
UPDATE `acp_gm_command_queue`
SET `status` = 'pending', `last_error` = 'auto-requeued stale processing row'
WHERE `status` = 'processing' AND TIMESTAMPDIFF(SECOND, `created_at`, NOW()) > 120;
