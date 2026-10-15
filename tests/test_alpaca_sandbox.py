import datetime as dt
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from experiments.alpaca_sandbox import AlpacaReadOnly, preflight

NOW=dt.datetime(2026,10,15,15,tzinfo=dt.timezone.utc)
class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class SandboxTests(unittest.TestCase):
    def test_missing_credentials_do_not_make_request(self):
        with self.assertRaisesRegex(ValueError,'credentials'):AlpacaReadOnly('', '')
    def test_fixed_endpoints_get_only_and_no_account_secrets_in_report(self):
        requests=[]
        def open_(req,timeout):
            requests.append(req)
            data={'status':'ACTIVE','trading_blocked':False,'account_blocked':False,'id':'PRIVATE','account_number':'PRIVATE'} if req.full_url.endswith('/account') else {'is_open':True,'timestamp':NOW.isoformat()} if req.full_url.endswith('/clock') else {'quotes':{'QQQ':{'t':NOW.isoformat(),'bp':100,'ap':101,'bs':10,'as':20}}}
            return Response(json.dumps(data).encode())
        c=AlpacaReadOnly('KEY','SECRET')
        with patch.object(c.opener,'open',side_effect=open_):r=preflight(c,now=NOW)
        self.assertTrue(r['fresh_quote']);self.assertFalse(r['ready_for_trading'])
        self.assertNotIn('PRIVATE',json.dumps(r));self.assertNotIn('SECRET',json.dumps(r))
        self.assertEqual(len(requests),3)
        self.assertTrue(all(x.get_method()=='GET' for x in requests))
        self.assertEqual(requests[0].full_url,'https://paper-api.alpaca.markets/v2/account')
        self.assertIn('feed=iex',requests[-1].full_url)
    def test_cannot_request_arbitrary_or_live_endpoint(self):
        c=AlpacaReadOnly('KEY','SECRET')
        for path in ['https://api.alpaca.markets/v2/account','orders','../orders']:
            with self.assertRaises(ValueError):c.get(path)
    def test_reject_redirect_does_not_forward_credentials(self):
        from urllib.request import Request
        c=AlpacaReadOnly('KEY','SECRET')
        handler=next(x for x in c.opener.handlers if hasattr(x,'redirect_request'))
        with self.assertRaises(HTTPError):handler.redirect_request(Request('https://paper-api.alpaca.markets/v2/account'),None,302,'redirect',{},'https://api.alpaca.markets/v2/account')
    def test_errors_do_not_echo_provider_body_or_credentials(self):
        c=AlpacaReadOnly('KEY','SECRET')
        with patch.object(c.opener,'open',side_effect=HTTPError('SECRET',401,'SECRET',{},None)):
            with self.assertRaisesRegex(RuntimeError,'HTTP 401') as e:c.get('account')
        self.assertNotIn('SECRET',str(e.exception))
    def test_bounded_response_and_invalid_json_fail(self):
        c=AlpacaReadOnly('KEY','SECRET')
        for payload in [b'x'*65537,b'[]',b'{']:
            with patch.object(c.opener,'open',return_value=Response(payload)):
                with self.assertRaises(ValueError):c.get('account')
    def test_stale_future_crossed_and_closed_not_fresh(self):
        for change in ['stale','future','crossed','closed']:
            def get(name,feed='iex'):
                if name=='account':return {'status':'ACTIVE','trading_blocked':False,'account_blocked':False}
                if name=='clock':return {'is_open':change!='closed','timestamp':NOW.isoformat()}
                t=NOW+dt.timedelta(seconds=-301 if change=='stale' else 1 if change=='future' else 0)
                return {'quotes':{'QQQ':{'t':t.isoformat(),'bp':102 if change=='crossed' else 100,'ap':101,'bs':10,'as':20}}}
            c=AlpacaReadOnly('KEY','SECRET');c.get=get
            self.assertFalse(preflight(c,now=NOW)['fresh_quote'])
    def test_unsupported_feed_rejected_before_network(self):
        c=AlpacaReadOnly('KEY','SECRET')
        with self.assertRaises(ValueError):c.get('quote',feed='delayed_sip')

    def test_malformed_quote_containers_fail_closed(self):
        c=AlpacaReadOnly('KEY','SECRET')
        for payload in [{'quotes':None},{'quotes':[]},{'quotes':{'QQQ':[]}}]:
            def get(name,feed='iex'):
                return payload if name=='quote' else {'status':'ACTIVE','is_open':True}
            c.get=get
            self.assertFalse(preflight(c,now=NOW)['fresh_quote'])
