"""Integration checks for preserved Quant Lab inputs and research tabs."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

from modules.options_payoff import trade_analysis
from modules.options_payoff_view import payoff_figure
from modules.premium_engine import demo_chain, generate


class QuantPayoffUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        return app.switch_page('pages/8_Quant_Lab.py').run()

    def test_manual_entry_and_research_tabs(self):
        app=self.app()
        app.radio[0].set_value('Enter my own trade').run()
        next(b for b in app.button if b.label=='Analyze my trade').click().run()
        self.assertFalse(app.exception)
        tabs=[t.label for t in app.tabs]
        for label in ('Portfolio research','Options stress lab','Pulse research','Methodology','Payoff map','Extreme stress'):
            self.assertIn(label,tabs)
        self.assertTrue(app.session_state['quant_manual_option'])
        self.assertIn('Maximum expiration loss',[m.label for m in app.metric])
        next(s for s in app.selectbox if s.label=='Research dataset').set_value('Synthetic demonstration')
        next(b for b in app.button if b.label=='Run research →').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state['quant_run_result'])

    def test_scanner_trade_and_public_tools(self):
        row=generate(demo_chain(30),500,30/365,.25)[0]
        row.update(symbol='SPY',source='Public · connected quotes',iv=.25,dte=30)
        app=self.app()
        app.session_state['quant_selected_option']=row
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Fetch selected contracts' history"==b.label for b in app.button))
        self.assertTrue(any('Provider Greek exposure' in m.value for m in app.markdown))
        next(n for n in app.number_input if n.label=='Strategy units').set_value(2).run()
        self.assertFalse(app.exception)
        self.assertEqual(next(m.value for m in app.metric if m.label=='Maximum expiration profit'),f"${row['max_profit']*2:,.2f}")

    def test_bad_saved_trade_does_not_break_research(self):
        app=self.app()
        app.session_state['quant_selected_option']={'spot':0,'legs':[]}
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertTrue(any(s.label=='Research dataset' for s in app.selectbox))

    def test_chart_landmarks_and_bounds(self):
        r=trade_analysis(dict(spot=769,credit=.18,shares=0,fees=0,
            legs=[dict(type='Put',strike=768,qty=-1),dict(type='Put',strike=767,qty=1)]))
        fig=payoff_figure(r)
        self.assertEqual({t.name for t in fig.data},{'Expiration P&L','Strikes','Breakevens','Current spot'})
        horizontal=[s.y0 for s in fig.layout.shapes if s.y0==s.y1]
        for value in (0,18,-82):
            self.assertIn(value,horizontal)


if __name__=='__main__':
    unittest.main()
