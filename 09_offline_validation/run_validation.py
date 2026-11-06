"""Temporal holdout validation of targeting rules; no treatment-effect claims.

Run from any directory. Only aggregated results are exported. Future events are
used exclusively for labels after rule-specific rankings have been computed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FEATURE_MAP = {
    'recent_intent': 'last_intent', 'intent_volume': 'intent_count',
    'cart_volume': 'cart_count', 'recent_activity': 'last_activity',
    'pv_volume': 'pv_count',
}

def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def build_features(events, decision_date, feature_start):
    """This function only receives or reads pre-decision events for features."""
    history = events.loc[events.date.ge(feature_start) & events.date.lt(decision_date)]
    counts = pd.crosstab(history.user_id, history.behavior_type).reindex(
        columns=['pv', 'fav', 'cart', 'buy'], fill_value=0)
    counts.columns = ['pv_count', 'fav_count', 'cart_count', 'buy_count']
    counts['intent_count'] = counts.fav_count + counts.cart_count
    counts['last_activity'] = history.groupby('user_id')['timestamp'].max()
    intents = history.loc[history.behavior_type.isin(['fav', 'cart'])]
    counts['last_intent'] = intents.groupby('user_id')['timestamp'].max()
    counts['active_days'] = history.groupby('user_id').date.nunique()
    # Stable tie-breaking independent of row order and future labels.
    counts['tie_key'] = [hashlib.blake2b(f'taobao-offline-v1:{u}'.encode(), digest_size=8).hexdigest()
                         for u in counts.index]
    broad = counts.loc[counts.buy_count.eq(0)].copy()
    eligible = broad.loc[broad.intent_count.gt(0)].copy()
    return counts, broad, eligible

def rank_users(features, rule):
    return features.sort_values([FEATURE_MAP[rule], 'tie_key'], ascending=[False, True]).index

def random_expectation(n, m, k, rng, draws):
    samples = rng.hypergeometric(m, n-m, k, size=draws)
    expected = k * m / n
    low, high = np.quantile(samples, [0.025, 0.975])
    return expected, float(low), float(high)

def evaluate_window(events, plan, name, rules, capacities, seed, draws):
    cfg = plan[name]
    all_features, broad, pool = build_features(events, cfg['decision_date'], cfg['feature_start'])
    assert not pool.empty
    # Feature-only rankings are fixed before any outcome labels are read below.
    ranked = {rule: rank_users(pool, rule) for rule in rules}
    future = events.loc[events.date.ge(cfg['decision_date']) & events.date.lt(cfg['outcome_end_exclusive'])]
    future_buyers = set(future.loc[future.behavior_type.eq('buy'), 'user_id'])
    n = len(pool)
    m = int(pool.index.isin(future_buyers).sum())
    broad_m = int(broad.index.isin(future_buyers).sum())
    rows = []
    rng = np.random.default_rng(seed)
    for capacity in capacities:
        k = min(capacity, n)
        expected, random_low, random_high = random_expectation(n, m, k, rng, draws)
        for rule in rules:
            hits = int(ranked[rule][:k].isin(future_buyers).sum())
            precision = hits/k
            baseline = m/n
            rows.append(dict(window=name, rule=rule, requested_capacity=capacity, selected_users=k,
                eligible_users=n, eligible_future_buyers=m, selected_future_buyers=hits,
                precision=precision, recall=hits/m if m else None,
                random_expected_buyers=expected, random_precision=baseline,
                random_recall=k/n, random_draw_p025_buyers=random_low, random_draw_p975_buyers=random_high,
                precision_gap_pp=100*(precision-baseline),
                precision_lift_ratio=precision/baseline if baseline else None,
                relative_lift_pct=100*(precision/baseline-1) if baseline else None,
                excess_observed_buyer_coverage=hits-expected,
                broad_nonbuyer_users=len(broad), broad_nonbuyer_future_buyers=broad_m,
                broad_random_expected_buyers=k*broad_m/len(broad)))
    metadata = dict(window=name, **cfg, observed_history_users=len(all_features),
        historical_nonbuyers=len(broad), intent_eligible_users=n,
        future_buyers_in_eligible=m, total_future_buyers=len(future_buyers),
        future_buyers_not_observed_in_history=len(future_buyers-set(all_features.index)))
    return pd.DataFrame(rows), metadata

def main(input_file, output_dir, plan_file):
    plan = json.loads(Path(plan_file).read_text(encoding='utf-8'))
    events = pd.read_csv(input_file, usecols=['user_id', 'behavior_type', 'timestamp', 'date'],
                         dtype={'user_id': 'int32', 'timestamp': 'int64', 'behavior_type': 'category'})
    if events.isna().any().any():
        raise ValueError('Missing input fields.')
    if not events.behavior_type.isin(['pv', 'fav', 'cart', 'buy']).all():
        raise ValueError('Unknown behavior type.')
    local_dates = pd.to_datetime(events.timestamp, unit='s', utc=True).dt.tz_convert('Asia/Shanghai').dt.strftime('%Y-%m-%d')
    if not local_dates.eq(events.date).all():
        raise ValueError('CSV dates disagree with Asia/Shanghai timestamps.')
    if not (events.date.ge('2017-11-25') & events.date.lt('2017-12-04')).all():
        raise ValueError('Unexpected analysis dates.')
    candidates = plan['candidate_rules_in_tie_priority_order']
    primary = plan['primary_capacity']
    valid, valid_meta = evaluate_window(events, plan, 'validation', candidates, [primary],
                                        plan['seed'], plan['random_baseline_draws'])
    # idxmax preserves prespecified candidate order on ties.
    selected_rule = str(valid.loc[valid.precision.idxmax(), 'rule'])
    print('Rule frozen from validation only:', selected_rule, flush=True)
    # All candidate comparisons are reported, but the rule is never reselected on test data.
    test, test_meta = evaluate_window(events, plan, 'test', candidates,
        plan['sensitivity_capacities'], plan['seed']+1, plan['random_baseline_draws'])
    robust, robust_meta = evaluate_window(events, plan, 'weekend_robustness', [selected_rule],
        plan['sensitivity_capacities'], plan['seed']+2, plan['random_baseline_draws'])
    results = pd.concat([valid, test, robust], ignore_index=True)
    results['selected_on_validation'] = results.rule.eq(selected_rule)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output/'strategy_comparison.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame([valid_meta, test_meta, robust_meta]).to_csv(output/'window_summary.csv', index=False, encoding='utf-8-sig')
    main_test = test.loc[test.rule.eq(selected_rule) & test.requested_capacity.eq(primary)].iloc[0].to_dict()
    main_robust = robust.loc[robust.requested_capacity.eq(primary)].iloc[0].to_dict()
    summary = dict(selected_rule=selected_rule, primary_capacity=primary,
        rule_chosen_using='validation outcomes only; test outcomes never select or tune rule',
        validation=valid.to_dict(orient='records'), test=main_test,
        weekend_robustness=main_robust, windows=[valid_meta, test_meta, robust_meta],
        input_rows=len(events), input_sha256=file_sha256(input_file),
        protocol_sha256=hashlib.sha256(Path(plan_file).read_bytes()).hexdigest(),
        numpy_version=np.__version__, pandas_version=pd.__version__,
        interpretation='Observed future-buyer identification / list coverage. No estimate of treatment uplift, causal conversion gain, GMV or ROI.')
    (output/'results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'selected_rule':selected_rule,'test':main_test,'weekend_robustness':main_robust},ensure_ascii=False,indent=2))
    return summary

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'02_processed_data/UserBehavior_clean.csv')
    parser.add_argument('--output', type=Path, default=HERE/'results')
    parser.add_argument('--protocol', type=Path, default=HERE/'protocol.json')
    args = parser.parse_args()
    main(args.input, args.output, args.protocol)
