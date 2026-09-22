from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from modules.market_state_research import build_research_dataset
from modules.historical_analogs import analog_research


def context(historical=False):
    prices=100+np.arange(230)*.02+np.sin(np.arange(230)/5)
    data=build_research_dataset(pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=230),symbol='SPY',
        open=prices,high=prices+1,low=prices-1,close=prices)),'2030-01-01',dict(source='UI fixture'))
    r=analog_research(data['features'],data['outcomes'],method='nearest',horizon=1,
        target_date=data['features'].date.iloc[180] if historical else None)
    r['target_mode']='HISTORICAL TARGET DATE' if historical else 'LATEST COMPLETED SESSION'
    r['sensitivity']=None
    r['dataset_identity']=(data['metadata']['source_ohlc_sha256'],'SPY',None)
    return data,r


class ThresholdUITests(unittest.TestCase):
    def app(self,historical=False,empty=False):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        if not empty:
            data,r=context(historical)
            app.session_state['market_state_result']=data
            app.session_state['historical_analog_result']=r
        return app.switch_page('pages/8_Quant_Lab.py').run()

    def submit(self,app):
        next(b for b in app.button if b.label=='Run threshold research').click().run()
        self.assertFalse(app.exception)

    def test_requires_saved_analogs(self):
        app=self.app(empty=True)
        self.assertFalse(app.exception)
        self.assertTrue(any('Generate Market State Research, then run Historical Analogs' in i.value for i in app.info))

    def test_percent_put_results_matrices_and_export(self):
        app=self.app()
        self.submit(app)
        r=app.session_state['threshold_research_result']
        self.assertAlmostEqual(r['config']['threshold_return'],-.015)
        self.assertEqual(len(r['grid']),30)
        for label in ('Distance grid & horizons','Distribution context','Non-overlapping robustness','Threshold observations'):
            self.assertIn(label,[t.label for t in app.tabs])
        self.assertIn('Historical analog terminal survival',[m.label for m in app.metric])
        self.assertTrue(any('95% Wilson interval for the observed historical frequency' in c.value for c in app.caption))
        self.assertTrue(any('Export threshold observations' in str(d.proto) for d in app.get('download_button')))

    def test_call_style_and_custom_grid(self):
        app=self.app()
        next(s for s in app.selectbox if s.label=='Threshold research mode').set_value('Short call style — BELOW')
        next(n for n in app.number_input if n.label=='Signed threshold distance (%)').set_value(1.5)
        next(t for t in app.text_input if t.label.startswith('Distance grid')).set_value('0.75, 1.25')
        self.submit(app)
        r=app.session_state['threshold_research_result']
        self.assertEqual(r['config']['mode'],'call')
        self.assertEqual(len(r['grid']),10)
        self.assertTrue((r['grid'].threshold_return>0).all())

    def test_opposite_side_requires_acknowledgement(self):
        app=self.app()
        next(n for n in app.number_input if n.label=='Signed threshold distance (%)').set_value(1.)
        self.submit(app)
        self.assertTrue(app.error)
        self.assertNotIn('threshold_research_result',app.session_state)
        next(c for c in app.checkbox if c.label.startswith('I intentionally')).set_value(True)
        self.submit(app)
        self.assertTrue(app.session_state['threshold_research_result']['config']['opposite_side'])
        self.assertTrue(any('OPPOSITE-SIDE THRESHOLD' in w.value for w in app.warning))

    def test_price_threshold_and_historical_trade_guard(self):
        app=self.app(historical=True)
        next(s for s in app.selectbox if s.label=='Threshold input').set_value('Price threshold').run()
        next(n for n in app.number_input if n.label=='Threshold price ($)').set_value(100.)
        self.submit(app)
        self.assertAlmostEqual(app.session_state['threshold_research_result']['config']['threshold_price'],100)
        next(s for s in app.selectbox if s.label=='Threshold input').set_value('Use short strike from selected trade').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Saved-trade shortcuts are disabled' in w.value for w in app.warning))
        self.assertFalse(any(b.label=='Run threshold research' for b in app.button))

    def test_condor_short_leg_selection_both_sides(self):
        app=self.app()
        app.session_state['quant_selected_option']=dict(symbol='SPY',spot=105.,credit=.4,shares=0,fees=0,
            source='Manual entry',expiration='2030-01-01',strategy='Iron condor',legs=[
                dict(type='Put',strike=100.,qty=-1),dict(type='Put',strike=99.,qty=1),
                dict(type='Call',strike=110.,qty=-1),dict(type='Call',strike=111.,qty=1)])
        next(s for s in app.selectbox if s.label=='Threshold input').set_value('Use short strike from selected trade').run()
        self.submit(app)
        self.assertEqual(app.session_state['threshold_research_result']['config']['mode'],'put')
        next(s for s in app.selectbox if s.label=='Short leg to research').set_value(1).run()
        self.submit(app)
        cfg=app.session_state['threshold_research_result']['config']
        self.assertEqual(cfg['mode'],'call')
        self.assertAlmostEqual(cfg['threshold_price'],110.)

    def test_new_analog_target_hides_previous_threshold_result(self):
        app=self.app()
        self.submit(app)
        data,r=context(historical=True)
        app.session_state['market_state_result']=data
        app.session_state['historical_analog_result']=r
        app.run()
        self.assertFalse(app.exception)
        self.assertNotIn('Historical analog terminal survival',[m.label for m in app.metric])


if __name__=='__main__':
    unittest.main()
