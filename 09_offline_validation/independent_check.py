"""Recompute primary-capacity results with streaming stdlib CSV and dictionaries.

This checker does not import the Pandas implementation. It checks all candidate
rules in validation and test, plus the frozen rule in the robustness window.
"""
from pathlib import Path
import csv
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCORE_INDEX = {'recent_intent':5, 'intent_volume':1, 'cart_volume':2,
               'recent_activity':4, 'pv_volume':3}

def main():
    plan = json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    summary = json.loads((HERE/'results/results.json').read_text(encoding='utf-8'))
    names = ['validation', 'test', 'weekend_robustness']
    histories = {n:{} for n in names}
    labels = {n:set() for n in names}
    with (ROOT/plan['source']).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            user, kind, day, stamp = int(row['user_id']), row['behavior_type'], row['date'], int(row['timestamp'])
            for name in names:
                window = plan[name]
                if window['feature_start'] <= day < window['decision_date']:
                    # bought / intent count / cart count / pv count / latest activity / latest intent
                    features = histories[name].setdefault(user,[0,0,0,0,-1,-1])
                    features[0] += kind == 'buy'
                    features[1] += kind in ('fav','cart')
                    features[2] += kind == 'cart'
                    features[3] += kind == 'pv'
                    features[4] = max(features[4],stamp)
                    if kind in ('fav','cart'): features[5] = max(features[5],stamp)
                elif window['decision_date'] <= day < window['outcome_end_exclusive'] and kind == 'buy':
                    labels[name].add(user)
    with (HERE/'results/strategy_comparison.csv').open(encoding='utf-8-sig',newline='') as stream:
        expected = {(r['window'],r['rule']):r for r in csv.DictReader(stream)
                    if int(r['requested_capacity']) == plan['primary_capacity']}
    checked = []
    for name in names:
        pool = {u:f for u,f in histories[name].items() if f[0] == 0 and f[1] > 0}
        buyers = labels[name] & pool.keys()
        k = min(plan['primary_capacity'],len(pool))
        rules = plan['candidate_rules_in_tie_priority_order'] if name != 'weekend_robustness' else [summary['selected_rule']]
        tie = {u:hashlib.blake2b(f'taobao-offline-v1:{u}'.encode(),digest_size=8).hexdigest() for u in pool}
        for rule in rules:
            ranking = sorted(pool,key=lambda u:(-pool[u][SCORE_INDEX[rule]],tie[u]))
            hits = len(set(ranking[:k]) & buyers)
            row = expected[name,rule]
            assert int(row['eligible_users']) == len(pool), (name,rule,'pool')
            assert int(row['eligible_future_buyers']) == len(buyers), (name,rule,'buyers')
            assert int(row['selected_future_buyers']) == hits, (name,rule,'hits')
            assert abs(float(row['random_expected_buyers'])-k*len(buyers)/len(pool)) < 1e-9
            checked.append(dict(window=name,rule=rule,eligible_users=len(pool),future_buyers=len(buyers),selected_hits=hits))
    result={'status':'passed','method':'stdlib CSV streaming independent of Pandas feature/label code',
            'primary_capacity':plan['primary_capacity'],'checked':checked}
    (HERE/'results/independent_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
