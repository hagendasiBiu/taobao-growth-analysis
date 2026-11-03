"""Read-only audit of existing CSVs; writes only to this review folder."""
from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent

def main():
    df = pd.read_csv(BASE / '02_processed_data/UserBehavior_clean.csv',
        usecols=['user_id','item_id','behavior_type','timestamp','date','hour'],
        dtype={'user_id':'int32','item_id':'int32','behavior_type':'category','timestamp':'int64','hour':'int8'})
    counts = df.behavior_type.value_counts()
    daily = df.groupby('date', observed=True).agg(events=('user_id','size'), uv=('user_id','nunique'))
    daily = daily.join(pd.crosstab(df.date, df.behavior_type))
    buy = df[df.behavior_type.eq('buy')]
    daily['buyers'] = buy.groupby('date').user_id.nunique()
    daily['buyer_rate_pct'] = daily.buyers / daily.uv * 100
    daily['weekend'] = pd.to_datetime(daily.index).dayofweek >= 5
    daily.to_csv(OUT / 'audit_daily.csv', encoding='utf-8-sig')
    hourly = pd.crosstab(df.hour, df.behavior_type)
    hourly.to_csv(OUT / 'audit_hourly.csv', encoding='utf-8-sig')
    buy_days = buy.groupby('user_id').date.nunique()
    activity = df[['user_id','date']].drop_duplicates()
    activity['date'] = pd.to_datetime(activity.date)
    first = activity.groupby('user_id').date.min().rename('first_date').reset_index()
    first = first[first.first_date.lt('2017-12-03')]
    first['next_date'] = first.first_date + pd.Timedelta(days=1)
    matched = first.merge(activity, left_on=['user_id','next_date'], right_on=['user_id','date'], how='left')
    matched['retained'] = matched.date.notna()
    cohort = matched.groupby('first_date').agg(users=('user_id','size'),retained=('retained','sum'))
    cohort['rate_pct'] = cohort.retained / cohort.users * 100
    cohort.to_csv(OUT/'audit_first_observed_retention.csv',encoding='utf-8-sig')
    # Compare the original rolling active-day retention, a different cohort definition.
    rolling = activity.copy()
    rolling['next_date'] = rolling.date + pd.Timedelta(days=1)
    rolling = rolling[rolling.date.lt('2017-12-03')]
    returned = rolling.merge(activity.rename(columns={'date':'returned_date'}),
        left_on=['user_id','next_date'],right_on=['user_id','returned_date'],how='left')
    returned['retained'] = returned.returned_date.notna()
    rolling_result = returned.groupby('date').agg(active_users=('user_id','size'),retained_users=('retained','sum'))
    shifts = {}
    for col in ['pv','uv','buy','buyers']:
        weekday = daily.loc[~daily.weekend,col].mean()
        weekend = daily.loc[daily.weekend,col].mean()
        shifts[col] = dict(weekday_daily_mean=float(weekday),weekend_daily_mean=float(weekend),growth_pct=float((weekend/weekday-1)*100))
    # Existence of a strictly ordered pv -> (fav or cart) -> buy path per user-item.
    keys=['user_id','item_id']
    pv = df[df.behavior_type.eq('pv')].groupby(keys,observed=True).timestamp.min().rename('pv_t').reset_index()
    intent = df[df.behavior_type.isin(['fav','cart'])][keys+['timestamp']].merge(pv,on=keys)
    intent = intent[intent.timestamp.gt(intent.pv_t)].groupby(keys).timestamp.min().rename('intent_t').reset_index()
    complete = buy[keys+['timestamp']].merge(intent,on=keys)
    complete = complete[complete.timestamp.gt(complete.intent_t)][keys].drop_duplicates()
    result = dict(rows=len(df),users=int(df.user_id.nunique()),behavior_counts={str(k):int(v) for k,v in counts.items()},
        buyers=int(len(buy_days)),cross_day_repeat_buyers=int(buy_days.ge(2).sum()),
        cross_day_repeat_pct=float(buy_days.ge(2).mean()*100),
        weekend_comparison=shifts,
        hourly_pv_top3=[int(x) for x in hourly.pv.nlargest(3).index],
        hourly_buy_top3=[int(x) for x in hourly.buy.nlargest(3).index],
        strict_funnel_user_item_pairs=dict(pv=len(pv),intent_after_pv=len(intent),buy_after_intent=len(complete)))
    old=pd.read_csv(BASE/'05_tableau/daily_behavior.csv').set_index('behavior_date')
    result['existing_daily_export_matches'] = bool((daily[['pv','fav','cart','buy']].astype(float).values == old[['pv','fav','cart','buy']].values).all())
    old_retention = pd.read_csv(BASE/'05_tableau/retention_1d.csv')
    result['existing_rolling_retention_counts_match'] = bool((rolling_result[['active_users','retained_users']].values == old_retention[['active_users','retained_users']].values).all())
    segments=pd.read_csv(BASE/'05_tableau/user_segments.csv')
    result['segment_export_user_sum']=int(segments.user_count.sum())
    result['segment_export_note']='Aggregated counts only; original assignment rules unavailable in project files.'
    (OUT/'audit_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print(cohort.to_string())

if __name__ == '__main__':
    main()
