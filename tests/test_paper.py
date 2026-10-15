import datetime as dt
import importlib.util
import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

class PaperTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('workers.quant_paper'),'paper ledger is missing')
        self.module=importlib.import_module('workers.quant_paper');self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.time=dt.datetime(2026,10,15,12,tzinfo=dt.timezone.utc)
        self.ledger=self.module.PaperLedger(self.root,clock=lambda:self.time)
        self.campaign=self.ledger.create(mode='recorded',source='synthetic fixture')['id']
    def tearDown(self):
        if hasattr(self,'ledger'):self.ledger.close();self.tmp.cleanup()
    def quote(self,day,size=1000000,**extra):
        date=dt.date(2025,1,1)+dt.timedelta(days=day)
        return dict(event_id=f'q{day}',symbol='QQQ',session=date.isoformat(),previous_session=(date-dt.timedelta(days=1)).isoformat() if day else None,
                    asof=date.isoformat()+'T20:00:00+00:00',bid='99',ask='101',bid_size=str(size),ask_size=str(size),**extra)
    def ingest(self,day,**kw):
        self.time+=dt.timedelta(seconds=1)
        return self.ledger.ingest(self.campaign,self.quote(day,**kw))
    def test_no_same_event_fill_and_independent_capital_affordability(self):
        a=self.ingest(0);self.assertTrue(all(b['shares']==0 for b in a['books']))
        b=self.ingest(1);books={r['key']:r for r in b['books']}
        self.assertGreater(books['buyhold:100']['shares'],0)
        self.assertGreater(books['buyhold:1000000']['shares'],books['buyhold:100']['shares'])
        self.assertTrue(all(r['cash']>=0 for r in b['books']))
        self.assertTrue(all(r['shares']==0 for r in b['books'] if r['strategy']!='buyhold'))
    def test_large_book_partial_fill_is_not_scaled_small_book(self):
        self.ingest(0);x=self.ingest(1,size=10);b={r['key']:r for r in x['books']}
        self.assertLessEqual(b['buyhold:1000000']['shares'],1)
        self.assertLess(b['buyhold:1000000']['shares']/1000000,b['buyhold:100']['shares']/100)
        self.assertTrue(any(r['status']=='partial' for r in x['recent_fills']))
    def test_duplicate_out_of_order_and_bad_quotes_do_not_mutate(self):
        self.ingest(0);before=self.ledger.export(self.campaign)
        for quote in [self.quote(0),dict(self.quote(1),ask='98'),dict(self.quote(1),bid='NaN')]:
            with self.assertRaises(ValueError):self.ledger.ingest(self.campaign,quote)
        self.assertEqual(before,self.ledger.export(self.campaign))
    def test_split_dividend_and_reopen_preserve_wealth_accounting(self):
        self.ingest(0);a=self.ingest(1);shares=a['books'][0]['shares'];self.ledger.control(self.campaign,True)
        self.time+=dt.timedelta(seconds=1);q=dict(self.quote(2),bid='49.5',ask='50.5',split_ratio='2',dividend_per_share='1')
        b=self.ledger.ingest(self.campaign,q)['books'][0]
        self.assertAlmostEqual(b['shares'],shares*2);self.assertAlmostEqual(b['equity'],a['books'][0]['equity']+shares*2)
        self.ledger.close();self.ledger=self.module.PaperLedger(self.root,clock=lambda:self.time)
        self.assertEqual(self.ledger.summary(self.campaign)['books'][0],b)
    def test_gap_halts_and_remains_ineligible_after_resume(self):
        self.ingest(0);self.time+=dt.timedelta(seconds=1)
        x=self.ledger.ingest(self.campaign,self.quote(2));self.assertTrue(x['halted']);self.assertFalse(x['evidence_complete'])
        self.assertTrue(all(b['shares']==0 for b in x['books']))
        self.assertFalse(self.ledger.control(self.campaign,False)['evidence_complete'])
    def test_prospective_rejects_old_future_and_precommit_quotes(self):
        cid=self.ledger.create(mode='prospective',source='manual unverified')['id']
        with self.assertRaises(ValueError):self.ledger.ingest(cid,self.quote(0))
        q=dict(self.quote(0),asof=(self.time+dt.timedelta(seconds=30)).isoformat())
        with self.assertRaises(ValueError):self.ledger.ingest(cid,q)
    def test_event_tamper_detected(self):
        self.ingest(0)
        self.ledger.db.execute("UPDATE paper_events SET digest='bad' WHERE campaign=? AND seq=1",(self.campaign,));self.ledger.db.commit()
        with self.assertRaises(ValueError):self.ledger.summary(self.campaign)
    def test_fee_minimum_and_rounding_do_not_overdraw_tiny_account(self):
        cid=self.ledger.create(mode='recorded',source='cost fixture',assumptions={'fixed_fee':'99','share_step':'1'})['id']
        self.ledger.ingest(cid,self.quote(0));x=self.ledger.ingest(cid,self.quote(1))
        small=next(r for r in x['books'] if r['key']=='buyhold:100');self.assertEqual(small['cash'],100);self.assertEqual(small['shares'],0)
    def test_missing_postcommit_receipt_fails_closed(self):
        self.ingest(0)
        self.ledger.db.execute('DELETE FROM paper_receipts WHERE campaign=?',(self.campaign,))
        with self.assertRaisesRegex(ValueError,'Unacknowledged'):self.ingest(1)
        self.assertEqual(self.ledger.summary(self.campaign)['quotes'],1)

    def test_changed_engine_can_be_exported_but_cannot_execute(self):
        self.ingest(0);self.ledger.engine_hash='different'
        self.assertFalse(self.ledger.summary(self.campaign)['engine_compatible'])
        self.assertTrue(self.ledger.export(self.campaign)['journal'])
        with self.assertRaises(ValueError):self.ingest(1)

    def test_all_fills_reconcile_cash_shares_fees_and_mark(self):
        from decimal import Decimal as D
        self.ingest(0);x=self.ingest(1)
        for fill in x['recent_fills']:
            if fill['quantity']=='0':continue
            book=next(b for b in x['books'] if b['key']==fill['book'])
            spent=D(fill['quantity'])*D(fill['price'])+D(fill['fee'])
            self.assertAlmostEqual(float(spent)+book['cash'],book['initial'],places=7)
            self.assertAlmostEqual(book['cash']+book['shares']*100,book['equity'],places=7)

    def test_forward_quote_after_durable_commit_is_accepted(self):
        cid=self.ledger.create(mode='prospective',source='locally observed fixture')['id']
        self.time+=dt.timedelta(seconds=60)
        q=dict(self.quote(0),session=self.time.date().isoformat(),asof=(self.time-dt.timedelta(seconds=1)).isoformat())
        x=self.ledger.ingest(cid,q);self.assertEqual(x['quotes'],1)
        receipts=self.ledger.export(cid)['commit_receipts'];self.assertEqual(len(receipts),2)
        self.assertGreater(q['asof'],receipts[0]['committed_not_after'])

    def test_calendar_returns_use_prior_year_equity_across_reopen(self):
        self.ingest(0);self.ingest(1);self.ledger.control(self.campaign,True)
        year_end=self.ingest(364)['books'][0]['equity']
        q=dict(self.quote(365),bid='109',ask='111');self.time+=dt.timedelta(seconds=1)
        book=self.ledger.ingest(self.campaign,q)['books'][0]
        self.assertAlmostEqual(book['calendar_returns']['2026']['return'],book['equity']/year_end-1)
        self.assertIsNone(book['rolling_252_return'])

    def test_fill_failure_rolls_back_all_books_and_journal(self):
        from unittest.mock import patch
        self.ingest(0);before=self.ledger.export(self.campaign)
        with patch.object(self.ledger,'_save',side_effect=RuntimeError('injected write failure')):
            with self.assertRaises(RuntimeError):self.ingest(1)
        self.assertEqual(before,self.ledger.export(self.campaign))

    def test_failure_after_durable_commit_blocks_retry_until_inspection(self):
        from unittest.mock import patch
        self.ingest(0)
        with patch.object(self.ledger,'_ack',side_effect=RuntimeError('injected receipt failure')):
            with self.assertRaises(RuntimeError):self.ingest(1)
        self.assertEqual(self.ledger.summary(self.campaign)['quotes'],2)
        with self.assertRaisesRegex(ValueError,'Unacknowledged'):self.ingest(2)
        self.assertTrue(self.ledger.control(self.campaign,True)['halted'])

    def test_receipt_timestamp_tampering_is_rejected(self):
        self.ingest(0)
        self.ledger.db.execute("UPDATE paper_receipts SET at='2020-01-01T00:00:00Z' WHERE campaign=? AND seq=1",(self.campaign,))
        with self.assertRaisesRegex(ValueError,'Unacknowledged'):self.ingest(1)

    def test_resume_does_not_fill_old_cancelled_targets(self):
        self.ingest(0);self.ledger.control(self.campaign,True);self.ingest(1);self.ledger.control(self.campaign,False)
        x=self.ingest(2);self.assertTrue(all(r['shares']==0 for r in x['books']))
        self.assertGreater(self.ingest(3)['books'][0]['shares'],0)

if __name__=='__main__':unittest.main()
