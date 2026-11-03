-- MySQL 8.0 学习答案，全部为只读查询。
-- 前提：user_behavior 是清洗后的九天样本；behavior_date 是中国时区日期。
-- CSV 的 date -> behavior_date；datetime -> behavior_time（教学约定）。
-- 原项目没有保存完整建表和导入脚本；先 DESCRIBE 核对实际字段。
-- 题1、2、4、5、6、7只依赖 user_id / behavior_type / behavior_date。
-- 题3、9从原始秒时间戳推导时间，避免依赖数据库会话时区。
-- 本次在 Pandas 明细中交叉核对指标，没有在 MySQL 服务中执行本文件。

-- 0. 先看字段和日期范围，别直接背答案。
DESCRIBE user_behavior;
SELECT COUNT(*) AS events, COUNT(DISTINCT user_id) AS users,
       MIN(behavior_date) AS start_date, MAX(behavior_date) AS end_date
FROM user_behavior;
-- 预期：4966986 / 49396 / 2017-11-25 / 2017-12-03。

-- 1. 每日PV、全行为UV、购买人数、购买事件次数。
SELECT behavior_date,
       SUM(CASE WHEN behavior_type='pv' THEN 1 ELSE 0 END) AS pv,
       COUNT(DISTINCT user_id) AS active_uv,
       COUNT(DISTINCT CASE WHEN behavior_type='pv' THEN user_id END) AS browse_uv,
       COUNT(DISTINCT CASE WHEN behavior_type='buy' THEN user_id END) AS buyers,
       SUM(CASE WHEN behavior_type='buy' THEN 1 ELSE 0 END) AS buy_events
FROM user_behavior
GROUP BY behavior_date
ORDER BY behavior_date;
-- 11月25日：PV456732，全行为UV35168，购买人数6518，购买事件9851。
-- 注意COUNT(CASE WHEN ... THEN 1 ELSE 0 END)会把0也计入，不能替代SUM。

-- 2. 日活跃用户购买率。分母包含所有行为，不是浏览用户转化率。
WITH daily AS (
 SELECT behavior_date, COUNT(DISTINCT user_id) AS active_uv,
        COUNT(DISTINCT CASE WHEN behavior_type='buy' THEN user_id END) AS buyers
 FROM user_behavior GROUP BY behavior_date
)
SELECT *, ROUND(100.0*buyers/NULLIF(active_uv,0),2) AS buyer_rate_pct
FROM daily ORDER BY behavior_date;

-- 3. 每小时购买次数；HOUR是0至23的小时桶。
WITH timed AS (
 SELECT behavior_type,
        TIMESTAMPADD(SECOND, `timestamp`, CAST('1970-01-01 08:00:00' AS DATETIME)) AS local_time
 FROM user_behavior
)
SELECT HOUR(local_time) AS behavior_hour, COUNT(*) AS buy_events
FROM timed WHERE behavior_type='buy'
GROUP BY HOUR(local_time) ORDER BY behavior_hour;
-- 20/21/22点分别6624/7137/6827。22点桶包含22:00至22:59:59。

-- 4. 买家在窗口内至少两个不同自然日购买的比例。
-- 同日买两次不算此定义的跨日复购；不要求连续两天。
WITH buyer_days AS (
 SELECT user_id, COUNT(DISTINCT behavior_date) AS purchase_days
 FROM user_behavior WHERE behavior_type='buy' GROUP BY user_id
)
SELECT COUNT(*) AS buyers,
       SUM(CASE WHEN purchase_days>=2 THEN 1 ELSE 0 END) AS repeat_buyers,
       ROUND(100.0*SUM(CASE WHEN purchase_days>=2 THEN 1 ELSE 0 END)
             /NULLIF(COUNT(*),0),2) AS repeat_rate_pct
FROM buyer_days;
-- 33620 / 18485 / 54.98%。不要对原始购买日志COUNT(*)充当买家分母。

-- 5. 窗口内首次观测活跃队列的次日留存，不能叫注册新客留存。
-- DISTINCT先压到用户日粒度，LEFT JOIN保留未回访用户。
WITH active AS (
 SELECT DISTINCT user_id, behavior_date FROM user_behavior
), first_seen AS (
 SELECT user_id, MIN(behavior_date) AS first_date FROM active GROUP BY user_id
), cohort AS (
 SELECT * FROM first_seen WHERE first_date<'2017-12-03'
)
SELECT c.first_date, COUNT(*) AS cohort_users,
       COUNT(a.user_id) AS retained_users,
       ROUND(100.0*COUNT(a.user_id)/NULLIF(COUNT(*),0),2) AS retention_pct
FROM cohort c
LEFT JOIN active a ON c.user_id=a.user_id
 AND a.behavior_date=DATE_ADD(c.first_date,INTERVAL 1 DAY)
GROUP BY c.first_date ORDER BY c.first_date;
-- 11月26日首次观测7978人，次日返回5276人，66.13%。
-- 最后一天无法观察次日，必须剔除；无队列的日期不会输出一行。

-- 6. 有浏览但整个窗口没有购买的用户；并非浏览某件商品未买该商品。
SELECT user_id
FROM user_behavior
GROUP BY user_id
HAVING SUM(CASE WHEN behavior_type='pv' THEN 1 ELSE 0 END)>0
   AND SUM(CASE WHEN behavior_type='buy' THEN 1 ELSE 0 END)=0;
-- 未购买者中也可能有完全没有PV但有收藏/加购的人，不能直接填15776。

-- 7. 按购买次数分层，阈值是新教学示例，不是原分层规则的还原。
WITH user_features AS (
 SELECT user_id,
        SUM(CASE WHEN behavior_type='buy' THEN 1 ELSE 0 END) AS buy_events
 FROM user_behavior GROUP BY user_id
), tagged AS (
 SELECT *, CASE WHEN buy_events=0 THEN '未购买'
                WHEN buy_events=1 THEN '购买1次'
                WHEN buy_events BETWEEN 2 AND 3 THEN '购买2至3次'
                ELSE '购买4次及以上' END AS purchase_segment
 FROM user_features
)
SELECT purchase_segment, COUNT(*) AS users, AVG(buy_events) AS avg_buy_events
FROM tagged GROUP BY purchase_segment;

-- 8. 工作日与周末比较必须统一日均。
-- WEEKDAY与Pandas dayofweek都以周一为0。不能使用跨四天去重UV除4替代日均DAU。
WITH daily AS (
 SELECT behavior_date, COUNT(DISTINCT user_id) AS active_uv,
        SUM(CASE WHEN behavior_type='pv' THEN 1 ELSE 0 END) AS pv,
        COUNT(DISTINCT CASE WHEN behavior_type='buy' THEN user_id END) AS buyers,
        SUM(CASE WHEN behavior_type='buy' THEN 1 ELSE 0 END) AS buy_events
 FROM user_behavior GROUP BY behavior_date
)
SELECT CASE WHEN WEEKDAY(behavior_date) IN (5,6) THEN '周末' ELSE '工作日' END AS day_type,
       COUNT(*) AS observed_days, AVG(pv) AS daily_pv, AVG(active_uv) AS daily_uv,
       AVG(buy_events) AS daily_buy_events, AVG(buyers) AS daily_buyers,
       100.0*SUM(buyers)/NULLIF(SUM(active_uv),0) AS pooled_buyer_rate_pct
FROM daily GROUP BY day_type;

-- 9. 严格路径：同一用户同一商品，存在pv时间 < 意向时间 < buy时间。
-- 先找最早PV，再找其后最早意向，最后判断意向后是否有购买。
-- 不能先取各行为全窗口首次时间再比较，这会漏掉后续有效路径。
WITH first_pv AS (
 SELECT user_id,item_id,MIN(`timestamp`) AS pv_time
 FROM user_behavior WHERE behavior_type='pv' GROUP BY user_id,item_id
), valid_intent AS (
 SELECT p.user_id,p.item_id,MIN(b.`timestamp`) AS intent_time
 FROM first_pv p JOIN user_behavior b ON p.user_id=b.user_id AND p.item_id=b.item_id
 AND b.behavior_type IN ('fav','cart') AND b.`timestamp`>p.pv_time
 GROUP BY p.user_id,p.item_id
), valid_buy AS (
 SELECT DISTINCT i.user_id,i.item_id
 FROM valid_intent i JOIN user_behavior b ON i.user_id=b.user_id AND i.item_id=b.item_id
 AND b.behavior_type='buy' AND b.`timestamp`>i.intent_time
)
SELECT (SELECT COUNT(*) FROM first_pv) AS viewed_pairs,
       (SELECT COUNT(*) FROM valid_intent) AS intent_pairs,
       (SELECT COUNT(*) FROM valid_buy) AS complete_pairs;
-- Pandas同口径重算：3528090 / 55988 / 5123。
-- 严格用>排除同秒事件；日志没有同秒事件先后顺序，不能自行猜测。

-- 10. 保留原Notebook的口径：任意当日活跃用户次日回访。
WITH active AS (
 SELECT DISTINCT user_id,behavior_date FROM user_behavior
)
SELECT a.behavior_date,COUNT(*) AS active_users,COUNT(b.user_id) AS returned_users,
       ROUND(100.0*COUNT(b.user_id)/NULLIF(COUNT(*),0),2) AS return_rate_pct
FROM active a LEFT JOIN active b ON a.user_id=b.user_id
 AND b.behavior_date=DATE_ADD(a.behavior_date,INTERVAL 1 DAY)
WHERE a.behavior_date<'2017-12-03'
GROUP BY a.behavior_date ORDER BY a.behavior_date;
