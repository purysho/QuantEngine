"""Read-only paper-account/quote preflight. Never submits or cancels orders."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise HTTPError(req.full_url,code,'Redirect refused',headers,fp)

class AlpacaReadOnly:
    def __init__(self,key,secret):
        if not key or not secret:raise ValueError('Paper API credentials are required in environment variables.')
        if any(c in key+secret for c in '\r\n'):raise ValueError('Invalid credentials.')
        self.headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
        self.opener=build_opener(NoRedirect())
    def get(self,name,feed='iex'):
        if feed not in ('iex','sip'):raise ValueError('Only explicit real-time IEX or entitled SIP feed supported.')
        urls={'account':'https://paper-api.alpaca.markets/v2/account',
              'clock':'https://paper-api.alpaca.markets/v2/clock',
              'quote':'https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=QQQ&feed='+feed}
        if name not in urls:raise ValueError('Read-only endpoint not allowed.')
        req=Request(urls[name],headers=self.headers,method='GET')
        try:
            with self.opener.open(req,timeout=15) as response:raw=response.read(65537)
        except HTTPError as exc:raise RuntimeError('Alpaca preflight HTTP '+str(exc.code)+'; response body withheld.') from None
        except (URLError,TimeoutError,OSError):raise RuntimeError('Alpaca preflight transport failed; details withheld.') from None
        if len(raw)>65536:raise ValueError('Provider response exceeds64KB.')
        try:data=json.loads(raw)
        except (ValueError,UnicodeError):raise ValueError('Invalid provider JSON.') from None
        if not isinstance(data,dict):raise ValueError('Provider response must be an object.')
        return data

def preflight(client,*,feed='iex',now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    account=client.get('account',feed=feed);clock=client.get('clock',feed=feed);payload=client.get('quote',feed=feed)
    quotes=payload.get('quotes')
    quote=quotes.get('QQQ',{}) if isinstance(quotes,dict) else {}
    if not isinstance(quote,dict):quote={}
    try:
        when=dt.datetime.fromisoformat(quote['t'].replace('Z','+00:00'))
        if when.tzinfo is None:raise ValueError('Timezone required.')
        age=(now-when).total_seconds()
        bid,ask=float(quote['bp']),float(quote['ap'])
        sizes=[float(quote[k]) for k in ('bs','as')]
        fresh=0<=age<=300 and all(math.isfinite(x) for x in [bid,ask,*sizes]) and ask>=bid>0 and min(sizes)>=0 and clock.get('is_open') is True
    except (KeyError,TypeError,ValueError,OverflowError):age=None;fresh=False
    return {'mode':'paper_read_only_preflight','observed_at':now.isoformat(),'provider':'Alpaca','symbol':'QQQ','feed':feed,
            'coverage':'single exchange IEX' if feed=='iex' else 'consolidated SIP; entitlement required',
            'account_active':account.get('status')=='ACTIVE' and account.get('trading_blocked') is False and account.get('account_blocked') is False,
            'market_open':clock.get('is_open') is True,'quote_age_seconds':age,'fresh_quote':fresh,
            'ready_for_trading':False,'orders_submitted':0,'independent_custody':False,
            'remaining_gates':['Calendar and corporate-action adapter','Audited quote-size units and provenance','Durable collector and restart/gap handling',
                               'Broker order lifecycle and fill reconciliation','External commitment custody','Always-on supervised runtime'],
            'notice':'Connectivity check only. No quote ingestion, order execution, performance measurement or capital certification.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--feed',choices=['iex','sip'],default='iex');p.add_argument('--output',required=True)
    args=p.parse_args()
    try:
        target=Path(args.output)
        if target.exists():raise ValueError('Use a new output path; preserve previous evidence.')
        client=AlpacaReadOnly(os.environ.get('QUANT_ALPACA_PAPER_KEY',''),os.environ.get('QUANT_ALPACA_PAPER_SECRET',''))
        report=preflight(client,feed=args.feed)
        # Exclusive creation avoids clobbering a simultaneous run. Never persist raw account data or keys.
        with target.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
        print(json.dumps(report,allow_nan=False))
        return 0 if report['account_active'] and report['fresh_quote'] else 2
    except (ValueError,RuntimeError,OSError) as exc:
        print('PREFLIGHT_NOT_READY: '+str(exc));return 2

if __name__=='__main__':raise SystemExit(main())
