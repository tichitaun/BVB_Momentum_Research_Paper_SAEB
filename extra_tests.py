"""
extra_tests.py - additional tests requested in the review (12-1 signal throughout).

A) Are the two legs different?  For each universe (core 7, fixed 13, rule-based 15), raw and
   sector-neutral: winner leg (winners - all), loser leg (all - losers), and their
   difference (loser leg - winner leg) with a Newey-West t-statistic. The difference is
   computed month by month, so it is a proper test of whether the legs differ.
B) Rule-based leave-one-out: each stock that was ever in the rule-based universe is removed
   from the pool, the universe is rebuilt (the next most liquid stock takes its place), and
   winners minus losers is recomputed.
C) Rule-based sub-periods and market alpha (the same tests as Table 4 for the fixed universe).
D) Market states: does momentum work only after the market has risen? Each formation month
   is classified as UP or DOWN by the BET-TR return over the previous 12 (and 24) months.
   Mean WML and loser leg in each state, and the difference (DOWN - UP) from a regression
   on a DOWN dummy, with Newey-West t-statistics.
Saves extra_tests.xlsx.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import (CORE, MAIN, K_MAIN, load_pool, membership, restrict, fixed_universe,
                    rule_based_universe, rf_for_holding_month, mean_test, stars, summarize,
                    print_table)
from portfolios import wml_series, leg_returns


def test_row(x, **labels):
    x = pd.Series(x).dropna().astype(float)
    mean, t, p = mean_test(x)
    return dict(**labels, annualized=mean * 12, t_NW=t, p=p, sig=stars(p), months=len(x))


def regression_on_dummy(y, dummy):
    """y = a + b * dummy; returns (a, b, t_b, p_b) with Newey-West (3 lags)."""
    data = pd.DataFrame({'y': y, 'd': dummy}).dropna().astype(float)
    fit = sm.OLS(data['y'], sm.add_constant(data['d'])).fit(cov_type='HAC', cov_kwds={'maxlags': 3})
    return fit.params['const'], fit.params['d'], fit.tvalues['d'], fit.pvalues['d']


if __name__ == '__main__':
    pd.set_option('display.width', 230)
    pd.set_option('display.max_rows', 300)

    index_m, pool = load_pool()
    universes = {'Core 7': {t: pool[t] for t in CORE if t in pool},
                 'Fixed 13': fixed_universe(pool),
                 f'Rule-based {K_MAIN}': rule_based_universe(pool)}

    # ------------------------------------------------------------------ A) legs and their difference
    A = []
    for universe, stocks in universes.items():
        for version, neutral in [('raw', False), ('sector-neutral', True)]:
            legs = leg_returns(stocks, MAIN, sector_neutral=neutral).astype(float)
            winner_leg = legs['winners'] - legs['all']
            loser_leg = legs['all'] - legs['losers']
            A.append(test_row(winner_leg, universe=universe, version=version, series='winner leg (winners - all)'))
            A.append(test_row(loser_leg, universe=universe, version=version, series='loser leg (all - losers)'))
            A.append(test_row(loser_leg - winner_leg, universe=universe, version=version,
                              series='difference (loser leg - winner leg)'))
    A = pd.DataFrame(A)
    print_table('A) Winner leg, loser leg and their difference (arithmetic annualised)', A)

    # ------------------------------------------------------------------ B) rule-based leave-one-out
    ever_in = [t for t, col in membership(pool, K_MAIN).items() if col.any()]
    B = []
    for ticker in ever_in:
        reduced = {t: m for t, m in pool.items() if t != ticker}
        stocks = restrict(reduced, membership(reduced, K_MAIN))
        B.append({'universe': f'Rule-based {K_MAIN}', **summarize(wml_series(stocks, MAIN), f'without {ticker}')})
    B = pd.DataFrame(B)
    print_table(f'B) Rule-based leave-one-out ({len(ever_in)} stocks)', B)

    # ------------------------------------------------------------------ C) rule-based sub-periods and alpha
    rule = universes[f'Rule-based {K_MAIN}']
    wml = wml_series(rule, MAIN)
    crisis = (wml.index >= pd.Period('2021-01', 'M')) & (wml.index <= pd.Period('2022-12', 'M'))
    C = [summarize(part, name) for name, part in [('formed 2016-2019', wml[:'2019-12']),
                                                   ('formed 2020-2025', wml['2020-01':]),
                                                   ('formed excl. 2021-2022', wml[~crisis])]]
    market_excess = index_m['next_1m'].reindex(wml.index) - rf_for_holding_month(wml.index)
    data = pd.DataFrame({'wml': wml, 'mkt': market_excess}).dropna().astype(float)
    fit = sm.OLS(data['wml'], sm.add_constant(data['mkt'])).fit(cov_type='HAC', cov_kwds={'maxlags': 3})
    C.append(dict(test='market alpha', mean_monthly=fit.params['const'], annualized=fit.params['const'] * 12,
                  t_NW=fit.tvalues['const'], p=fit.pvalues['const'], sig=stars(fit.pvalues['const']),
                  months=len(data), pct_positive=np.nan, market_beta=fit.params['mkt'],
                  t_beta=fit.tvalues['mkt']))
    C = pd.DataFrame(C)
    print_table(f'C) Rule-based {K_MAIN}: sub-periods and market alpha (WML, 12-1)', C)

    # ------------------------------------------------------------------ D) market states
    price = index_m['Price']
    D = []
    for horizon in [12, 24, 36]:            # 36 months is the definition used by Cooper et al. (2004)
        past_market = price / price.shift(horizon) - 1                 # known at the end of month t
        for universe in ['Fixed 13', f'Rule-based {K_MAIN}']:
            stocks = universes[universe]
            legs = leg_returns(stocks, MAIN).astype(float)
            series = {'WML': legs['winners'] - legs['losers'], 'loser leg': legs['all'] - legs['losers']}
            past = past_market.reindex(legs.index)
            down = (past <= 0).astype(float).where(past.notna())   # months without enough history: excluded
            for name, y in series.items():
                up, dn = y[down == 0], y[down == 1]
                if len(dn) == 0:                                  # no falling-market month at all
                    D.append(dict(state_signal=f'BET-TR past {horizon} months', universe=universe, series=name,
                                  months_UP=len(up), mean_UP_annual=up.mean() * 12, t_UP=mean_test(up)[1],
                                  months_DOWN=0, first_month_with_data=str(past.dropna().index.min())))
                    continue
                up_mean, diff, t_diff, p_diff = regression_on_dummy(y, down)
                t_up = mean_test(up)[1] if len(up) > 5 else np.nan
                t_dn = mean_test(dn)[1] if len(dn) > 5 else np.nan
                D.append(dict(state_signal=f'BET-TR past {horizon} months', universe=universe, series=name,
                              months_UP=len(up), mean_UP_annual=up.mean() * 12, t_UP=t_up,
                              months_DOWN=len(dn), mean_DOWN_annual=dn.mean() * 12, t_DOWN=t_dn,
                              DOWN_minus_UP_annual=diff * 12, t_difference=t_diff, p_difference=p_diff))
    D = pd.DataFrame(D)
    print_table('D) Momentum after rising (UP) and falling (DOWN) markets', D)

    with pd.ExcelWriter('extra_tests.xlsx') as xw:
        A.to_excel(xw, sheet_name='A_legs_difference', index=False)
        B.to_excel(xw, sheet_name='B_rule_leave_one_out', index=False)
        C.to_excel(xw, sheet_name='C_rule_subperiods_alpha', index=False)
        D.to_excel(xw, sheet_name='D_market_states', index=False)
    print('\nSaved extra_tests.xlsx')
