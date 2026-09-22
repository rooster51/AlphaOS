from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from modules.daily_archive import archive_path,write_artifact


class DailyArchiveUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        with patch('modules.daily_archive_workspace.DATA_ROOT',self.root):
            return app.switch_page('pages/8_Quant_Lab.py').run()
    def add(self,day):
        symbols={s:dict(status='complete',market_state=dict(close=100.,ema_structure='mixed'),
            historical_analogs=dict(final_n=20,sample_warning='Small sample',outcome_summaries=[])) for s in ('SPY','QQQ')}
        write_artifact(archive_path(self.root,'research',day),dict(schema_version='daily-quant-v1',session_date=day,
            generated_at=day+'T22:23:00+00:00',config_version='daily-quant-config-v1',status='complete',warnings=['Fixture warning'],symbols=symbols))
        write_artifact(archive_path(self.root,'options',day,'SPY'),dict(schema_version='options-archive-v1',snapshot_date=day,
            symbol='SPY',config_version='daily-quant-config-v1',status='complete',valid_contracts=[{}],questionable_contracts=[{}],rejected_contracts=[],
            generated_at=day+'T22:24:00+00:00',quote_timing='last_available_not_guaranteed_close',warnings=['Quote timing unverified'],rejection_counts={}))

    def test_empty_archive_and_existing_tabs_preserved(self):
        app=self.app();self.assertFalse(app.exception)
        self.assertIn('Daily Archive',[t.label for t in app.tabs])
        self.assertTrue(any('No daily snapshots' in i.value for i in app.info))
        self.assertIn('Market State Research',[t.label for t in app.tabs])
        self.assertIn('Threshold Research',[t.label for t in app.tabs])

    def test_latest_and_historical_archives_with_separate_options(self):
        self.add('2026-09-21');self.add('2026-09-22')
        app=self.app();self.assertFalse(app.exception)
        self.assertEqual(next(m.value for m in app.metric if m.label=='Latest daily research date'),'2026-09-22')
        self.assertTrue(any('1 valid · 1 questionable · 0 rejected' in c.value for c in app.caption))
        with patch('modules.daily_archive_workspace.DATA_ROOT',self.root):
            next(s for s in app.selectbox if s.label=='Archived session').set_value('2026-09-21').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('2026-09-21T22:23' in c.value for c in app.caption))
        self.assertTrue(any('QQQ options snapshot is absent' in i.value for i in app.info))
        self.assertTrue(any('Download daily research JSON' in str(d.proto) for d in app.get('download_button')))

    def test_bad_file_warns_without_using_stale_manifest(self):
        (self.root/'daily_quant').mkdir()
        (self.root/'daily_quant'/'2026-09-22.json').write_text('bad')
        (self.root/'archive_manifest.json').write_text('{"latest_research":"fake"}')
        app=self.app();self.assertFalse(app.exception)
        self.assertTrue(any('unreadable or inconsistent' in w.value for w in app.warning))


if __name__=='__main__': unittest.main()
