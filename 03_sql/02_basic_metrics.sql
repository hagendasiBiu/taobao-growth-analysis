-- =========================================================
-- 1. 整体核心指标
-- =========================================================

SELECT
    COUNT(*) AS total_behavior_count,

    COUNT(DISTINCT user_id) AS uv,

    SUM(behavior_type = 'pv') AS pv,

    COUNT(DISTINCT CASE
        WHEN behavior_type = 'buy' THEN user_id
    END) AS buyer_count,

    SUM(behavior_type = 'buy') AS buy_count,

    ROUND(
        SUM(behavior_type = 'pv') /
        COUNT(DISTINCT user_id),
        2
    ) AS avg_pv_per_user,

    ROUND(
        SUM(behavior_type = 'buy') /
        COUNT(DISTINCT CASE
            WHEN behavior_type = 'buy' THEN user_id
        END),
        2
    ) AS avg_buy_per_buyer

FROM user_behavior;

-- =========================================================
-- 2. 用户行为结构
-- =========================================================

SELECT
    behavior_type,
    COUNT(*) AS behavior_count,
    ROUND(
        COUNT(*) * 100.0 /
        SUM(COUNT(*)) OVER (),
        2
    ) AS behavior_pct
FROM user_behavior
GROUP BY behavior_type
ORDER BY behavior_count DESC;

-- =========================================================
-- 3. 每日活跃情况
-- =========================================================

SELECT
    behavior_date,

    COUNT(*) AS behavior_count,

    COUNT(DISTINCT user_id) AS dau,

    SUM(behavior_type = 'pv') AS pv,

    COUNT(DISTINCT CASE
        WHEN behavior_type = 'buy' THEN user_id
    END) AS buyer_count,

    SUM(behavior_type = 'buy') AS buy_count

FROM user_behavior
GROUP BY behavior_date
ORDER BY behavior_date;

-- =========================================================
-- 4. 每日购买用户转化
-- =========================================================

SELECT
    behavior_date,

    COUNT(DISTINCT user_id) AS active_users,

    COUNT(DISTINCT CASE
        WHEN behavior_type = 'buy' THEN user_id
    END) AS buyer_users,

    ROUND(
        COUNT(DISTINCT CASE
            WHEN behavior_type = 'buy' THEN user_id
        END)
        /
        COUNT(DISTINCT user_id)
        * 100,
        2
    ) AS buyer_conversion_rate

FROM user_behavior
GROUP BY behavior_date
ORDER BY behavior_date;

-- =========================================================
-- 5. 工作日 / 周末行为对比
-- =========================================================

SELECT
    CASE
        WHEN is_weekend = 1 THEN '周末'
        ELSE '工作日'
    END AS day_type,

    COUNT(*) AS behavior_count,

    COUNT(DISTINCT user_id) AS users,

    SUM(behavior_type = 'pv') AS pv,

    SUM(behavior_type = 'buy') AS buy_count

FROM user_behavior
GROUP BY is_weekend
ORDER BY is_weekend;