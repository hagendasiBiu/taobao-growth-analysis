-- MySQL 8.0. Create an isolated local analysis database before importing.
CREATE DATABASE IF NOT EXISTS taobao_growth CHARACTER SET utf8mb4;
USE taobao_growth;

CREATE TABLE IF NOT EXISTS user_behavior (
    user_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    behavior_type VARCHAR(8) NOT NULL,
    `timestamp` BIGINT NOT NULL,
    behavior_time DATETIME NOT NULL,
    behavior_date DATE NOT NULL,
    hour TINYINT NOT NULL,
    weekday TINYINT NOT NULL,
    weekday_name VARCHAR(8) NOT NULL,
    is_weekend TINYINT NOT NULL,
    INDEX idx_user_date (user_id, behavior_date),
    INDEX idx_behavior (behavior_type),
    INDEX idx_date (behavior_date)
);
