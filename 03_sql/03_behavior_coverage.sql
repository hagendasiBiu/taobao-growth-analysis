-- =========================================================
-- 1. 各行为阶段覆盖用户数
-- =========================================================

SELECT
    behavior_type,
    COUNT(*) AS behavior_count,
    COUNT(DISTINCT user_id) AS user_count,
    ROUND(
        COUNT(DISTINCT user_id) /
        (SELECT COUNT(DISTINCT user_id)
         FROM user_behavior) * 100,
        2
    ) AS user_coverage_rate
FROM user_behavior
GROUP BY behavior_type
ORDER BY
    FIELD(behavior_type, 'pv', 'fav', 'cart', 'buy');