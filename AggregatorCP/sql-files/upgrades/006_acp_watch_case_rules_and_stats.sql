-- Extend Watch Center with criteria-based rules, thresholds and execution stats

ALTER TABLE `acp_watch_cases`
  ADD COLUMN IF NOT EXISTS `checks_count` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `notes`,
  ADD COLUMN IF NOT EXISTS `monitor_any_change` TINYINT(1) NOT NULL DEFAULT 1 AFTER `checks_count`,
  ADD COLUMN IF NOT EXISTS `monitor_item_movement` TINYINT(1) NOT NULL DEFAULT 0 AFTER `monitor_any_change`,
  ADD COLUMN IF NOT EXISTS `item_movement_threshold` INT UNSIGNED NOT NULL DEFAULT 20 AFTER `monitor_item_movement`,
  ADD COLUMN IF NOT EXISTS `monitor_failed_logins` TINYINT(1) NOT NULL DEFAULT 0 AFTER `item_movement_threshold`,
  ADD COLUMN IF NOT EXISTS `failed_login_threshold` INT UNSIGNED NOT NULL DEFAULT 5 AFTER `monitor_failed_logins`,
  ADD COLUMN IF NOT EXISTS `monitor_zeny_increase` TINYINT(1) NOT NULL DEFAULT 0 AFTER `failed_login_threshold`,
  ADD COLUMN IF NOT EXISTS `zeny_increase_threshold` BIGINT UNSIGNED NOT NULL DEFAULT 1000000 AFTER `monitor_zeny_increase`;
