"""Maturity-safe Phase 3 outcomes shared by Phase 6 diagnostics."""
import numpy as np
from modules.threshold_survival import _prepare_sample


def prepared_outcomes(analog_result, horizon):
    frame, _ = _prepare_sample(analog_result, horizon)
    names = [f'future_{kind}_{horizon}s' for kind in ('return', 'high_excursion', 'low_excursion')]
    x = frame[['date', *names]].copy()
    x.columns = ['date', 'terminal_return', 'up_excursion', 'down_excursion']
    invalid = ((x.up_excursion < x.down_excursion - 1e-12) |
               (x.terminal_return > x.up_excursion + 1e-12) |
               (x.terminal_return < x.down_excursion - 1e-12))
    x.loc[invalid, ['terminal_return', 'up_excursion', 'down_excursion']] = np.nan
    return x
