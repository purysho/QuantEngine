"""Local, capital-aware paper books. No network or brokerage capability."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import sys
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
import sqlite3
import uuid
from contextlib import contextmanager

D=Decimal
SCALES=[100,10000,1000000]
DEFAULTS={'share_step':'0.000001','minimum_notional':'1','fee_bps':'10','fixed_fee':'0','max_participation':'0.1','impact_bps':'10'}


def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(encode(x).encode()).hexdigest()
def timestamp(value):
    if not isinstance(value,str):raise ValueError('Timestamp required.')
    t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('Timestamp must include timezone.')
    return t.astimezone(dt.timezone.utc)
def number(value,low='0',high='1000000000000'):
    if isinstance(value,bool):raise ValueError('Boolean is not a number.')
    try:n=D(str(value))
    except Exception as exc:raise ValueError('Invalid decimal.') from exc
    if not n.is_finite() or n<D(low) or n>D(high):raise ValueError('Numeric input outside limits.')
    return n


class PaperLedger:
    def __init__(self,root,clock=None):
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(root/'paper.sqlite3',timeout=10,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS paper_campaigns(id TEXT PRIMARY KEY, config TEXT, state TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS paper_events(campaign TEXT,seq INTEGER,previous TEXT,digest TEXT,event TEXT,state TEXT,PRIMARY KEY(campaign,seq))')
        self.db.execute('CREATE TABLE IF NOT EXISTS paper_receipts(campaign TEXT, seq INTEGER, head TEXT, at TEXT, receipt_sha TEXT, PRIMARY KEY(campaign,seq))')
        self.clock=clock or (lambda:dt.datetime.now(dt.timezone.utc))
        self.engine_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def close(self):self.db.close()
    @contextmanager
    def atomic(self,write=True):
        self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:yield;self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    def _load(self,cid,require_engine=False):
        row=self.db.execute('SELECT config,state FROM paper_campaigns WHERE id=?',(cid,)).fetchone()
        if row is None:raise ValueError('Unknown paper campaign.')
        config,state=map(json.loads,row);previous='0'*64;last=None
        for seq,prev,h,event,saved in self.db.execute('SELECT seq,previous,digest,event,state FROM paper_events WHERE campaign=? ORDER BY seq',(cid,)):
            event=json.loads(event);saved=json.loads(saved)
            if prev!=previous or saved['sequence']!=seq or digest({'previous':prev,'event':event,'state':saved})!=h:raise ValueError('Paper journal integrity failure.')
            if seq==0 and event.get('config')!=config:raise ValueError('Frozen configuration changed.')
            previous=h;last=saved
        if last!=state:raise ValueError('Paper state does not match journal.')
        if require_engine and (config['engine_sha256']!=self.engine_hash or config['python_version']!=sys.version.split()[0]):raise ValueError('Paper engine changed; preserve this campaign and start a new frozen campaign.')
        return config,state,previous
    def _save(self,cid,state,event,previous):
        if state['sequence']>5000:raise ValueError('Paper journal event limit reached.')
        h=digest({'previous':previous,'event':event,'state':state})
        self.db.execute('INSERT INTO paper_events VALUES(?,?,?,?,?,?)',(cid,state['sequence'],previous,h,encode(event),encode(state)))
        self.db.execute('UPDATE paper_campaigns SET state=? WHERE id=?',(encode(state),cid))
    def _ack(self,cid):
        # Sample only AFTER target transaction has durably committed. Missing ACK fails closed.
        with self.atomic():
            _,state,head=self._load(cid)
            at=self.clock().astimezone(dt.timezone.utc).isoformat()
            if timestamp(at)<timestamp(state["received_at"]):raise ValueError("Clock regressed after commit.")
            self.db.execute("INSERT OR REPLACE INTO paper_receipts VALUES(?,?,?,?,?)",(cid,state["sequence"],head,at,digest([cid,state["sequence"],head,at])))
    def create(self,*,mode,source,assumptions=None):
        if mode not in ['recorded','prospective'] or not isinstance(source,str) or not 1<=len(source)<=120:raise ValueError('Choose mode and a source label of1–120 characters.')
        assumptions={} if assumptions is None else assumptions
        if not isinstance(assumptions,dict) or set(assumptions)-set(DEFAULTS):raise ValueError('Unknown execution assumption.')
        settings={**DEFAULTS,**assumptions}
        for k,v in settings.items():settings[k]=str(number(v,high='1000'))
        if not D('0')<D(settings['share_step'])<=1 or not D('0')<D(settings['max_participation'])<=1:raise ValueError('Invalid share step/participation.')
        created=self.clock().astimezone(dt.timezone.utc).isoformat();cid=uuid.uuid4().hex
        config={'id':cid,'created_at':created,'mode':mode,'source':source,'symbol':'QQQ','scales':SCALES,'assumptions':settings,
                'engine_sha256':self.engine_hash,'python_version':sys.version.split()[0],'strategies':['buyhold','vol15_interval1','vol15_interval5'],
                'rules':'15%/20-close total-return volatility;10pp band;21 observed quotes warmup;next-session target execution',
                'limitations':['Local source/clock and quotes are unverified; no independent custody.','Snapshot liquidity/impact are assumptions, not proven capacity.',
                              'Cash interest zero; personal taxes and data/runtime costs excluded.','Each book is an independent alternative portfolio, not simultaneous liquidity demand.']}
        books=[{'key':f'{strategy}:{capital}','strategy':strategy,'initial':str(capital),'cash':str(capital),'shares':'0','equity':str(capital),'peak':str(capital),'drawdown':'0','fees':'0','target':'0','last_update':-21,'pending':None,'unfilled':0}
               for capital in SCALES for strategy in config['strategies']]
        state={'sequence':0,'quotes':0,'received_at':created,'last_quote':None,'halted':False,'evidence_complete':True,'books':books,'prices':[],'recent_fills':[],'alerts':[],'first_session':None}
        with self.atomic():
            if self.db.execute('SELECT COUNT(*) FROM paper_campaigns').fetchone()[0]>=50:raise ValueError('Paper campaign limit50 reached.')
            self.db.execute('INSERT INTO paper_campaigns VALUES(?,?,?)',(cid,encode(config),encode(state)))
            self._save(cid,state,{'operation':'create','config':config},'0'*64)
        self._ack(cid)
        return self.summary(cid)
    def _fill(self,book,quote,config,weight):
        a={k:D(v) for k,v in config['assumptions'].items()};cash=D(book['cash']);shares=D(book['shares'])
        mid=(D(quote['bid'])+D(quote['ask']))/2;desired=(cash+shares*mid)*D(weight)/mid-shares
        side='buy' if desired>0 else 'sell';available=D(quote['ask_size' if side=='buy' else 'bid_size'])
        limit=min(abs(desired),available*a['max_participation'])
        if side=='sell':limit=min(limit,shares)
        step=a['share_step'];roundq=lambda x:(max(D(0),x)/step).to_integral_value(rounding=ROUND_DOWN)*step
        def execution(q):
            impact=a['impact_bps']/10000*(q/available).sqrt() if available>0 else D(0)
            price=D(quote['ask'])*(1+impact) if side=='buy' else D(quote['bid'])*(1-impact)
            notional=q*price;fee=notional*a['fee_bps']/10000+a['fixed_fee']
            return price,notional,fee
        q=roundq(limit)
        if side=='buy' and q>0 and sum(execution(q)[1:])>cash:
            lo=D(0);hi=q
            for _ in range(64):
                test=(lo+hi)/2
                if sum(execution(test)[1:])<=cash:lo=test
                else:hi=test
            q=roundq(lo)
        price,notional,fee=execution(q)
        if q<=0 or notional<a['minimum_notional'] or (side=='sell' and notional<fee):
            if abs(desired)*mid>=a['minimum_notional']:book['unfilled']+=1
            return {'book':book['key'],'side':side,'status':'no_order' if abs(desired)*mid<a['minimum_notional'] or desired==0 else 'unfilled','quantity':'0','fee':'0','reason':'rounding/minimum/affordability/quoted liquidity','session':quote['session']}
        cash=cash-notional-fee if side=='buy' else cash+notional-fee
        shares=shares+q if side=='buy' else shares-q
        if cash<0 or shares<0:raise ArithmeticError('Paper fill overdraw.')
        book.update(cash=str(cash),shares=str(shares),fees=str(D(book['fees'])+fee))
        partial=q+step<abs(desired)
        if partial:book['unfilled']+=1
        return {'book':book['key'],'side':side,'status':'partial' if partial else 'filled','quantity':str(q),'price':str(price),'fee':str(fee),'session':quote['session'],
                'reason':'Residual IOC quantity expires; subsequent decisions may retry.' if partial else ''}
    def ingest(self,cid,quote):
        if not isinstance(quote,dict) or len(encode(quote))>8000:raise ValueError('One bounded quote object required.')
        allowed={'event_id','symbol','session','previous_session','asof','bid','ask','bid_size','ask_size','split_ratio','dividend_per_share'}
        if set(quote)-allowed or not set(['event_id','symbol','session','previous_session','asof','bid','ask','bid_size','ask_size'])<=set(quote):raise ValueError('Invalid quote schema.')
        q=dict(quote)
        if not isinstance(q['event_id'],str) or not 1<=len(q['event_id'])<=100 or q['symbol']!='QQQ':raise ValueError('Invalid quote identifier/symbol.')
        session=dt.date.fromisoformat(q['session']);asof=timestamp(q['asof']);received=self.clock().astimezone(dt.timezone.utc)
        if asof>received or asof.date()!=session:raise ValueError('Future quote or session/asof mismatch.')
        if q['previous_session'] is not None:dt.date.fromisoformat(q['previous_session'])
        for key in ['bid','ask','bid_size','ask_size']:q[key]=str(number(q[key]))
        q['split_ratio']=str(number(q.get('split_ratio','1'),low='0.000001',high='10000'))
        q['dividend_per_share']=str(number(q.get('dividend_per_share','0')))
        if D(q['bid'])<=0 or D(q['ask'])<D(q['bid']):raise ValueError('Invalid/crossed quote.')
        with self.atomic():
            config,s,previous=self._load(cid,True);last=s['last_quote']
            receipt=self.db.execute('SELECT seq,head,at,receipt_sha FROM paper_receipts WHERE campaign=? ORDER BY seq DESC LIMIT 1',(cid,)).fetchone()
            if receipt is None or receipt[0]!=s['sequence'] or receipt[1]!=previous or receipt[3]!=digest([cid,*receipt[:3]]):raise ValueError('Unacknowledged durable commit; halt and inspect before resuming.')
            if s['quotes']>=2000:raise ValueError('Campaign observation limit reached.')
            if received<timestamp(s['received_at']):raise ValueError('Local receipt clock regressed.')
            if self.db.execute("SELECT 1 FROM paper_events WHERE campaign=? AND json_extract(event,'$.quote.event_id')=?",(cid,q['event_id'])).fetchone():raise ValueError('Duplicate event.')
            if last and (q['session']<=last['session'] or asof<=timestamp(last['asof'])):raise ValueError('Quote is not chronologically new.')
            if config['mode']=='prospective' and ((received-asof).total_seconds()>300 or asof<=timestamp(receipt[2])):raise ValueError('Prospective quote stale or predates durable decision.')
            gap=(last is not None and (q['previous_session']!=last['session'] or (session-dt.date.fromisoformat(last['session'])).days>7))
            if gap:
                s['halted']=True;s['evidence_complete']=False;s['alerts'].append('Session gap: execution halted; prior targets cancelled. Evidence remains incomplete.')
            mid=(D(q['bid'])+D(q['ask']))/2;split=D(q['split_ratio']);dividend=D(q['dividend_per_share']);fills=[]
            for book in s['books']:
                shares=D(book['shares'])*split;book['shares']=str(shares);book['cash']=str(D(book['cash'])+shares*dividend)
                if not s['halted'] and book['pending'] is not None:fills.append(self._fill(book,q,config,book['pending']))
                book['pending']=None
                equity=D(book['cash'])+D(book['shares'])*mid
                if equity>D('1e15') or D(book['shares'])>D('1e12'):raise ValueError('Paper account exceeds bounded simulation limits.')
                peak=max(D(book['peak']),equity)
                book.update(equity=str(equity),peak=str(peak),drawdown=str(min(D(book['drawdown']),equity/peak-1)))
            # Total-return feature level handles splits and ex-distribution price drops.
            if gap:s['prices']=[]
            level=float(mid) if not s['prices'] or not last else s['prices'][-1]*float((mid+dividend)*split/((D(last['bid'])+D(last['ask']))/2))
            s['prices']=(s['prices']+[level])[-21:];s['quotes']+=1
            import statistics
            vol=statistics.stdev([math.log(b/a) for a,b in zip(s['prices'][:-1],s['prices'][1:])])*math.sqrt(252) if len(s['prices'])==21 else None
            for book in s['books']:
                target=D(1) if book['strategy']=='buyhold' else D(str(min(1.,.15/max(vol,1e-12)))) if vol is not None else D(0)
                interval=1 if book['strategy']=='buyhold' else int(book['strategy'][-1])
                if book['strategy']=='buyhold' or (s['quotes']-book['last_update']>=interval and (book['last_update']<0 and vol is not None or abs(target-D(book['target']))>=D('.1'))):
                    book['target']=str(target);book['last_update']=s['quotes']
                book['pending']=book['target'] if not s['halted'] else None
            s.update(sequence=s['sequence']+1,received_at=received.isoformat(),last_quote=q,recent_fills=fills,first_session=s['first_session'] or q['session'])
            self._save(cid,s,{'operation':'quote','quote':q,'received_at':received.isoformat()},previous)
        self._ack(cid)
        return self.summary(cid)
    def control(self,cid,halted):
        if type(halted) is not bool:raise ValueError('Halt must be boolean.')
        with self.atomic():
            _,s,previous=self._load(cid,not halted);now=self.clock().astimezone(dt.timezone.utc)
            if now<timestamp(s['received_at']):raise ValueError('Local clock regressed.')
            s.update(halted=halted,sequence=s['sequence']+1,received_at=now.isoformat())
            for b in s['books']:b['pending']=None
            self._save(cid,s,{'operation':'halt' if halted else 'resume','at':now.isoformat()},previous)
        self._ack(cid)
        return self.summary(cid)
    def summary(self,cid=None):
        with self.atomic(False):
            campaigns=[{'id':id,'source':json.loads(config)['source'],'mode':json.loads(config)['mode']} for id,config in self.db.execute('SELECT id,config FROM paper_campaigns ORDER BY rowid DESC')]
            if cid is None:cid=campaigns[0]['id'] if campaigns else None
            if cid is None:return {'campaigns':[],'active':None,'feed_status':'No campaign or quote feed connected.'}
            config,s,h=self._load(cid)
            curve=[];annual={};prior={b['key']:b['initial'] for b in s['books']}
            for saved, in self.db.execute("SELECT state FROM paper_events WHERE campaign=? AND json_extract(event,'$.operation')='quote' ORDER BY seq",(cid,)):
                point=json.loads(saved);session=point['last_quote']['session'];equities={b['key']:b['equity'] for b in point['books']}
                curve.append({'session':session,'equity':equities})
                for key,equity in equities.items():
                    period=annual.setdefault(session[:4],{}).setdefault(key,{'start_equity':prior[key],'start_session':session,'end_session':session,'end_equity':equity})
                    period.update(end_session=session,end_equity=equity)
                prior=equities
            books=[]
            for b in s['books']:
                row={**b,**{k:float(D(b[k])) for k in ['initial','cash','shares','equity','drawdown','fees','target']}}
                benchmark=next(x for x in s['books'] if x['key']=='buyhold:'+b['initial'])
                row.update(net_return=float(D(b['equity'])/D(b['initial'])-1),excess_dollars=float(D(b['equity'])-D(benchmark['equity'])))
                days=(dt.date.fromisoformat(s['last_quote']['session'])-dt.date.fromisoformat(s['first_session'])).days if s['last_quote'] else 0
                row['cagr']=float((float(D(b['equity'])/D(b['initial'])))**(365.25/days)-1) if days>=365 else None
                row['calendar_returns']={year:{**data,'return':float(D(data['end_equity'])/D(data['start_equity'])-1) if D(data['start_equity'])>0 else None} for year,rows in annual.items() if (data:=rows.get(b['key'])) is not None}
                row['rolling_252_return']=float(D(b['equity'])/D(curve[-253]['equity'][b['key']])-1) if len(curve)>=253 and D(curve[-253]['equity'][b['key']])>0 else None
                books.append(row)
            return {**s,'curve':curve[-400:],'books':books,'id':cid,'config':config,'campaigns':campaigns,'journal_sha256':h,
                    'feed_status':'Awaiting a supplied daily quote feed.' if not s['quotes'] else 'Locally received observations; source and timestamps not independently verified.',
                    'quote_age_seconds':max(0,(self.clock()-timestamp(s['last_quote']['asof'])).total_seconds()) if s['last_quote'] else None,
                    'mark_basis':'midpoint; future liquidation costs excluded','engine_compatible':config['engine_sha256']==self.engine_hash and config['python_version']==sys.version.split()[0],'custody':'local_unverified','capacity_status':'modeled_assumptions_only','warmup_quotes':max(0,21-len(s['prices']))}
    def export(self,cid):
        with self.atomic(False):
            config,s,h=self._load(cid)
            return {'config':config,'state':s,'journal_sha256':h,'commit_receipts':[{'sequence':seq,'head':head,'committed_not_after':at,'sha256':h} for seq,head,at,h in self.db.execute('SELECT seq,head,at,receipt_sha FROM paper_receipts WHERE campaign=? ORDER BY seq',(cid,))],'journal':[{'sequence':seq,'previous':prev,'sha256':hash,'event':json.loads(e),'state':json.loads(state)} for seq,prev,hash,e,state in self.db.execute('SELECT seq,previous,digest,event,state FROM paper_events WHERE campaign=? ORDER BY seq',(cid,))]}
