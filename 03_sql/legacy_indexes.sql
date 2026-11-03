USE taobao_growth;

SELECT COUNT(*) AS total_rows
FROM user_behavior;

ALTER TABLE user_behavior
ADD INDEX idx_user (user_id),
ADD INDEX idx_date (behavior_date),
ADD INDEX idx_behavior (behavior_type),
ADD INDEX idx_category (category_id),
ADD INDEX idx_user_date (user_id, behavior_date);

SHOW INDEX FROM user_behavior;