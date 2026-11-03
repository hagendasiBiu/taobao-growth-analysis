# 本地处理数据

运行 `python scripts/prepare_data.py` 后，在本目录生成 `UserBehavior_clean.csv`。
规则：保留user_id模20为0的用户，Unix秒转Asia/Shanghai，限制2017-11-25至2017-12-03。
该明细不会提交到Git。原始样本和清洗CSV仍保留在项目的本地工作目录中。
