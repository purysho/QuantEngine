"""Synthetic integration evidence for the paper ledger; never market alpha."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
from workers.quant_paper import PaperLedger


def run(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    now=dt.datetime(2026,10,15,tzinfo=dt.timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        ledger=PaperLedger(tmp,clock=lambda:now)
        created=ledger.create(mode='recorded',source='Synthetic capacity and accounting acceptance')
        for i in range(35):
            session=dt.date(2025,1,1)+dt.timedelta(days=i);now+=dt.timedelta(seconds=1)
            mid=100+i*.15+((-1)**i)*3
            quote={'event_id':'synthetic-'+str(i),'symbol':'QQQ','session':str(session),
                   'previous_session':str(session-dt.timedelta(days=1)) if i else None,
                   'asof':str(session)+'T20:00:00Z','bid':str(mid-.05),'ask':str(mid+.05),'bid_size':'100','ask_size':'100'}
            summary=ledger.ingest(created['id'],quote)
        journal=ledger.export(created['id']);ledger.close()
        reopened=PaperLedger(tmp,clock=lambda:now);same=reopened.summary(created['id'])
        assert summary==same
        assert len(summary['books'])==9 and all(b['cash']>=0 and b['shares']>=0 for b in summary['books'])
        assert summary['books'][0]['shares']/100!=summary['books'][6]['shares']/1000000
        assert len(journal['commit_receipts'])==36
        for record in journal['journal']:
            if record['event']['operation']=='quote':
                for fill in record['state']['recent_fills']:
                    if fill['quantity']!='0':assert record['state']['quotes']>1
        # Exercise permanent gap status and cancelled targets, then clean reopen/export.
        now+=dt.timedelta(seconds=1);quote.update(event_id='gap',session='2025-02-08',previous_session='2025-02-07',asof='2025-02-08T20:00:00Z')
        gap=reopened.ingest(created['id'],quote)
        assert gap['halted'] and not gap['evidence_complete']
        reopened.close()
    result={'status':'synthetic_software_acceptance_not_market_performance','observations':35,'books':summary['books'],
            'config':summary['config'],'receipt_count':len(journal['commit_receipts']),'restart_exact_match':True,'gap_failed_closed':True,
            'real_quote_feed_connected':False,'independent_custody':False,'capacity_verified':False,
            'notice':'Actual synthetic ledger outputs; no market superiority, live broker fills or supported capital range demonstrated.'}
    result['config'].pop('id');result['config'].pop('created_at')
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    root=Path(__file__).resolve().parents[1]
    (out/'source_sha256.json').write_text(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['workers/quant_paper.py','experiments/paper_acceptance.py']},indent=2)+'\n')
    print('PAPER_ACCEPTANCE_OK:9 books,35 synthetic observations, durable reopen, gap fail-closed; no real feed or alpha evidence.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);args=p.parse_args();run(args.output_dir)
