"""Load cleaned CSV into an empty table created by 03_sql/01_schema.sql."""
from pathlib import Path
import os
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]

def main():
    url = URL.create('mysql+pymysql',
        username=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'],
        host=os.environ.get('MYSQL_HOST', 'localhost'),
        port=int(os.environ.get('MYSQL_PORT', '3306')),
        database=os.environ.get('MYSQL_DATABASE', 'taobao_growth'),
        query={'charset':'utf8mb4'})
    engine = create_engine(url)
    csv_path = ROOT/'02_processed_data/UserBehavior_clean.csv'
    if not csv_path.is_file():
        raise FileNotFoundError('Run scripts/prepare_data.py first.')
    with engine.begin() as conn:
        # The schema must already exist. Never drop or replace existing data.
        if conn.execute(text('SELECT COUNT(*) FROM user_behavior')).scalar_one() != 0:
            raise ValueError('Table is not empty. Refusing duplicate import.')
        total = 0
        for frame in pd.read_csv(csv_path, chunksize=50_000):
            frame = frame.rename(columns={'date':'behavior_date', 'datetime':'behavior_time'})
            frame['behavior_time'] = pd.to_datetime(frame.behavior_time)
            frame['behavior_date'] = pd.to_datetime(frame.behavior_date).dt.date
            frame.to_sql('user_behavior', conn, if_exists='append', index=False, chunksize=1000)
            total += len(frame)
        print(f'Loaded {total:,} events. Commit occurs on successful completion.')
    engine.dispose()

if __name__ == '__main__':
    main()
