import copy
import json
import unittest
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd
from public_api_sdk.exceptions import ValidationError as PublicValidationError

from modules.public_history import fetch_research_bars, research_request
from modules.history_diagnostics import HistoryError
from modules.market_state_research import build_research_dataset, load_market_state
from modules.market_state import validate_ohlc

AS_OF = '2026-09-22'


def response(symbol='SPY',period='SINCE_PURCHASE',start='2016-09-22',end=AS_OF):
    dates = pd.bdate_range(start,end)
    bars = [dict(timestamp=d.isoformat()+'Z',open='100',high='102',low='99',close='101',value='101',volume='1000') for d in dates]
    return dict(symbol=symbol,period=period,totalExpectedBars=len(bars),
                preMarket=dict(expectedBars=0,bars=[]),regularMarket=dict(expectedBars=len(bars),bars=bars),
                afterMarket=dict(expectedBars=0,bars=[]))


def client_for(raw):
    client = Mock()
    client.api_client.get.return_value = raw
    return client


class PublicHistoryTests(unittest.TestCase):
    def fetch(self,raw,period='TEN_YEARS',symbol='SPY'):
        return fetch_research_bars(client_for(raw),symbol,period,as_of=AS_OF)

    def test_actual_rejected_period_aggregation_regression(self):
        client = client_for(response())
        def get(path,params):
            if '/TEN_YEARS/' in path:
                raise PublicValidationError('Period TEN_YEARS is not compatible with aggregation ONE_DAY',400)
            self.assertEqual(path,'/userapigateway/historicdata/EQUITY/SPY/SINCE_PURCHASE/ONE_DAY')
            self.assertEqual(params,{'purchaseDate':'2016-09-22'})
            return response()
        client.api_client.get.side_effect = get
        frame = fetch_research_bars(client,'SPY','TEN_YEARS',as_of=AS_OF)
        self.assertGreater(len(frame),2500)
        client.api_client.get.assert_called_once()

    def test_period_mapping(self):
        for period in ('MONTH','YEAR','FIVE_YEARS'):
            path,params,mapped,start=research_request('SPY',period,'EQUITY',AS_OF)
            self.assertTrue(path.endswith(f'/{period}/ONE_DAY'))
            self.assertEqual(mapped,period)
            self.assertIsNone(params)
            self.assertIsNone(start)
        self.assertEqual(research_request('SPY','TEN_YEARS','EQUITY','2024-02-29')[1],{'purchaseDate':'2014-02-28'})

    def test_unsupported_periods_no_network(self):
        for period in ('MAX','ALL','10y','TWO_YEARS'):
            client=Mock()
            with self.assertRaisesRegex(ValueError,'Unsupported research period'):
                fetch_research_bars(client,'SPY',period,as_of=AS_OF)
            client.api_client.get.assert_not_called()

    def test_valid_long_history_all_four_combinations_features(self):
        for symbol in ('SPY','QQQ'):
            for period,start,mapped in (('TEN_YEARS','2016-09-22','SINCE_PURCHASE'),('FIVE_YEARS','2021-09-22','FIVE_YEARS')):
                with self.subTest(symbol=symbol,period=period):
                    frame=self.fetch(response(symbol,mapped,start),period,symbol)
                    dataset=build_research_dataset(frame.assign(symbol=symbol),AS_OF)
                    self.assertTrue(dataset['features'].ema_200.iloc[-1]>0)
                    self.assertEqual(dataset['metadata']['end'],'2026-09-21')
                    self.assertEqual(len(dataset['features']),len(frame)-1)
                    self.assertEqual(frame.attrs['provider_diagnostics']['excluded_uncompleted'],1)

    def test_duplicate_dates_rejected_with_reason(self):
        raw=response();raw['regularMarket']['bars'][1]['timestamp']=raw['regularMarket']['bars'][0]['timestamp']
        with self.assertRaisesRegex(HistoryError,'duplicate session dates') as caught:
            self.fetch(raw)
        self.assertEqual(caught.exception.diagnostics['duplicate_dates'],1)
        self.assertEqual(caught.exception.diagnostics['stage'],'ohlc_validation')

    def test_timezone_normalized_duplicate(self):
        raw=response();raw['regularMarket']['bars'][1]['timestamp']='2016-09-21T20:00:00-04:00'
        with self.assertRaisesRegex(HistoryError,'duplicate session dates'):
            self.fetch(raw)

    def test_invalid_ohlc_bounds_not_repaired(self):
        raw=response();raw['regularMarket']['bars'][4]['high']='100'
        with self.assertRaisesRegex(HistoryError,'Invalid OHLC bounds on 2016-09-28') as caught:
            self.fetch(raw)
        self.assertEqual(caught.exception.diagnostics['inconsistent_ohlc_rows'],1)

    def test_null_ohlc_schema_not_bypassed(self):
        raw=response();raw['regularMarket']['bars'][2]['close']=None
        with self.assertRaisesRegex(HistoryError,'schema') as caught:
            self.fetch(raw)
        diagnostic=caught.exception.diagnostics
        self.assertEqual(diagnostic['null_ohlc'],1)
        self.assertEqual(diagnostic['schema_issues'][0]['field'],'regularMarket.bars.2.close')
        self.assertEqual(diagnostic['stage'],'provider_schema')

    def test_missing_ohlc_field_schema(self):
        raw=response();del raw['regularMarket']['bars'][3]['open']
        with self.assertRaises(HistoryError) as caught:
            self.fetch(raw)
        self.assertEqual(caught.exception.diagnostics['schema_issues'][0]['code'],'missing')

    def test_nonpositive_and_nonfinite_ohlc(self):
        for value in ('0','-1','Infinity','NaN'):
            raw=response();raw['regularMarket']['bars'][0]['low']=value
            with self.subTest(value=value),self.assertRaises(HistoryError):
                self.fetch(raw)

    def test_truncated_ten_years_not_accepted_as_five(self):
        with self.assertRaisesRegex(HistoryError,'truncated or unavailable') as caught:
            self.fetch(response(start='2021-09-22'))
        self.assertEqual(caught.exception.diagnostics['stage'],'coverage_validation')
        self.assertEqual(caught.exception.diagnostics['first_date'],'2021-09-22')

    def test_stale_end_rejected(self):
        with self.assertRaisesRegex(HistoryError,'stale or truncated'):
            self.fetch(response(end='2026-08-20'))

    def test_coarse_monthly_response_rejected(self):
        raw=response();raw['regularMarket']['bars']=raw['regularMarket']['bars'][::21]
        with self.assertRaises(HistoryError):
            self.fetch(raw)

    def test_no_shorter_fallback_on_http_failure_and_secret_redaction(self):
        client=Mock()
        client.api_client.get.side_effect=PublicValidationError('SECRET_TOKEN_123 Authorization Bearer ABCXYZ invalid aggregation',400,{'token':'SECRET_TOKEN_123'})
        with self.assertRaises(HistoryError) as caught:
            fetch_research_bars(client,'SPY','TEN_YEARS',as_of=AS_OF)
        client.api_client.get.assert_called_once_with('/userapigateway/historicdata/EQUITY/SPY/SINCE_PURCHASE/ONE_DAY',params={'purchaseDate':'2016-09-22'})
        rendered=str(caught.exception)+json.dumps(caught.exception.diagnostics)
        for secret in ('SECRET','ABCXYZ','Authorization','Bearer'):
            self.assertNotIn(secret,rendered)
        self.assertEqual(caught.exception.diagnostics['http_status'],400)
        self.assertIsNone(caught.exception.diagnostics['returned_rows'])

    def test_schema_error_does_not_expose_input(self):
        raw=response();raw['regularMarket']['bars'][0]['open']='secret-api-token'
        with self.assertRaises(HistoryError) as caught:
            self.fetch(raw)
        self.assertNotIn('secret-api-token',json.dumps(caught.exception.diagnostics))

    def test_no_adjusted_close_substitution(self):
        raw=response()
        for bar in raw['regularMarket']['bars']:
            bar['adjustedClose']='50'
        frame=self.fetch(raw)
        self.assertTrue((frame.close==101).all())
        self.assertTrue((frame.open==100).all())
        self.assertIn('unverified',frame.attrs['provider_diagnostics']['adjustment'])

    def test_wrong_symbol_or_period_rejected(self):
        for key,value in (('symbol','QQQ'),('period','FIVE_YEARS')):
            raw=response();raw[key]=value
            with self.assertRaisesRegex(HistoryError,'does not match'):
                self.fetch(raw)

    def test_leading_fill_rejected(self):
        raw=response();raw['leadingFill']={'count':10,'value':'100'}
        with self.assertRaisesRegex(HistoryError,'synthetic leading-fill'):
            self.fetch(raw)

    def test_empty_or_bad_envelope(self):
        for raw in ([],{},response(start='2026-09-23',end=AS_OF)):
            with self.subTest(raw_type=type(raw)),self.assertRaises(HistoryError):
                self.fetch(raw)

    def test_missing_interior_rows_not_filled(self):
        raw=response();del raw['regularMarket']['bars'][50:65]
        with self.assertRaisesRegex(HistoryError,'sparse or not daily'):
            self.fetch(raw)

    def test_history_error_preserved_by_market_state_and_portfolio(self):
        error=HistoryError('Public rejected the requested period.',dict(symbol='SPY',requested_period='TEN_YEARS',stage='provider_request'))
        from modules.public_research import load_public_research
        with patch('modules.public_data.get_public_research_bars',side_effect=error):
            for call in (lambda:load_market_state('SPY','TEN_YEARS'),lambda:load_public_research(['SPY'],'TEN_YEARS')):
                with self.assertRaises(HistoryError) as caught:
                    call()
                self.assertIs(caught.exception,error)

    def test_weekend_observation_rejected(self):
        raw=response();raw['regularMarket']['bars'][1]['timestamp']='2016-09-24T00:00:00Z'
        with self.assertRaisesRegex(HistoryError,'Weekend'):
            self.fetch(raw)

    def test_invalid_and_unsorted_dates(self):
        for value in ('not-a-date','2010-01-01T00:00:00Z'):
            raw=response();raw['regularMarket']['bars'][2]['timestamp']=value
            with self.assertRaises(HistoryError):
                self.fetch(raw)

    def test_strict_bounds_remain_unchanged(self):
        frame=pd.DataFrame(dict(date=['2020-01-02'],symbol=['SPY'],open=[100.],low=[99.],high=[100.],close=[np.nextafter(100.,np.inf)]))
        with self.assertRaisesRegex(ValueError,'Invalid OHLC bounds'):
            validate_ohlc(frame,AS_OF)


if __name__=='__main__':
    unittest.main()
