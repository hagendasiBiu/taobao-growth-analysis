"""Checks temporal boundaries, user eligibility and ranking stability."""
import unittest
import pandas as pd
from run_validation import build_features, rank_users, evaluate_window

def event(user, behavior, time):
    stamp = pd.Timestamp(time, tz='Asia/Shanghai')
    return dict(user_id=user, behavior_type=behavior, timestamp=int(stamp.timestamp()), date=stamp.strftime('%Y-%m-%d'))

class TemporalValidationTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame([
            event(100,'cart','2017-11-27 23:59:59'),
            event(120,'fav','2017-11-27 12:00:00'),
            event(140,'buy','2017-11-26 12:00:00'),
            event(140,'cart','2017-11-27 13:00:00'),
            event(160,'pv','2017-11-27 14:00:00')])

    def test_future_events_do_not_change_features_or_eligibility(self):
        future = pd.DataFrame([event(100,'buy','2017-11-28 00:00:00'),
            event(180,'cart','2017-11-28 01:00:00'), event(160,'cart','2017-11-29 01:00:00')])
        before = build_features(self.history,'2017-11-28','2017-11-25')
        after = build_features(pd.concat([self.history,future]),'2017-11-28','2017-11-25')
        for a,b in zip(before,after): pd.testing.assert_frame_equal(a,b)
        self.assertEqual(set(after[2].index),{100,120})
        self.assertEqual(set(after[1].index),{100,120,160})

    def test_horizon_is_two_days_and_future_only_users_are_excluded(self):
        future = pd.DataFrame([event(100,'buy','2017-11-28 00:00:00'),
            event(120,'buy','2017-11-30 00:00:00'), event(180,'buy','2017-11-29 23:59:59')])
        plan={'validation':{'feature_start':'2017-11-25','decision_date':'2017-11-28','outcome_end_exclusive':'2017-11-30'}}
        result,meta=evaluate_window(pd.concat([self.history,future]),plan,'validation',['recent_intent'],[1],1,100)
        row=result.iloc[0]
        self.assertEqual(row.eligible_users,2)
        self.assertEqual(row.eligible_future_buyers,1)
        self.assertEqual(row.selected_future_buyers,1)
        self.assertEqual(row.random_expected_buyers,0.5)
        self.assertEqual(meta['future_buyers_not_observed_in_history'],1)

    def test_rank_is_invariant_to_input_order_and_ties(self):
        tied=pd.DataFrame([event(100,'cart','2017-11-27 12:00:00'),event(120,'cart','2017-11-27 12:00:00')])
        a=build_features(tied,'2017-11-28','2017-11-25')[2]
        b=build_features(tied.iloc[::-1],'2017-11-28','2017-11-25')[2]
        self.assertEqual(rank_users(a,'intent_volume').tolist(),rank_users(b,'intent_volume').tolist())

if __name__=='__main__': unittest.main()
