"""Reproduce user-level sampling and China-time window filtering, in chunks."""
from pathlib import Path
import argparse
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLS = ['user_id', 'item_id', 'category_id', 'behavior_type', 'timestamp']

def prepare(input_path, output_path, chunk_size=1_000_000):
    input_path, output_path = Path(input_path), Path(output_path)
    if not input_path.is_file():
        raise FileNotFoundError(f'Download UserBehavior.csv first: {input_path}')
    if output_path.exists():
        raise FileExistsError(f'Refusing to overwrite existing data: {output_path}')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix('.partial')
    if temporary.exists():
        raise FileExistsError(f'Inspect previous partial output first: {temporary}')
    total, sampled, kept, first = 0, 0, 0, True
    for chunk in pd.read_csv(input_path, names=COLS, chunksize=chunk_size):
        total += len(chunk)
        frame = chunk.loc[chunk.user_id.mod(20).eq(0)].copy()
        sampled += len(frame)
        if frame.empty:
            continue
        if frame[COLS].isna().any().any():
            raise ValueError('Missing values in sampled raw fields; inspect source data.')
        if not frame.behavior_type.isin(['pv', 'fav', 'cart', 'buy']).all():
            raise ValueError('Unknown behavior type; inspect source data.')
        local = pd.to_datetime(frame.timestamp, unit='s', utc=True).dt.tz_convert('Asia/Shanghai')
        frame['datetime'] = local.dt.tz_localize(None)
        frame = frame.loc[frame['datetime'].ge('2017-11-25') & frame['datetime'].lt('2017-12-04')].copy()
        if frame.empty:
            continue
        frame['date'] = frame['datetime'].dt.date
        frame['hour'] = frame['datetime'].dt.hour
        frame['weekday'] = frame['datetime'].dt.dayofweek
        frame['weekday_name'] = frame.weekday.map(dict(enumerate(['周一','周二','周三','周四','周五','周六','周日'])))
        frame['is_weekend'] = frame.weekday.isin([5, 6]).astype(int)
        frame.to_csv(temporary, mode='w' if first else 'a', header=first, index=False,
                     encoding='utf-8-sig' if first else 'utf-8')
        first = False
        kept += len(frame)
    if first:
        raise ValueError('No records remain in the configured user sample and date window.')
    temporary.rename(output_path)
    result = {'raw_rows': total, 'sample_rows': sampled, 'clean_rows': kept,
              'removed_outside_window': sampled-kept}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'01_raw_data/UserBehavior.csv')
    parser.add_argument('--output', type=Path, default=ROOT/'02_processed_data/UserBehavior_clean.csv')
    parser.add_argument('--chunk-size', type=int, default=1_000_000)
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error('--chunk-size must be positive')
    prepare(args.input, args.output, args.chunk_size)
