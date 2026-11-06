"""
size_tests.py - is the loser effect a small-company effect? (review step 5)

INPUT: market_cap.csv, one row per company and year, with the year-end market cap in lei in a
column called market_cap_ron (or market_cap_lei), for example from the BVB December monthly
reports (template: market_cap_template.csv):
    ticker,year,market_cap_lei,source
    TLV,2014,7350000000,BVB annual statistics 2014
market_cap_lei = the company's stock market value at the END of that year, in lei
(shares outstanding x closing price on the last trading day of the year), from the BVB
statistics or the company's annual report. Leave out years before the company was listed.

HOW SIZE IS MEASURED EACH MONTH (only with information known at month t):
    size(i, t) = market cap at the end of the previous year x  Close(t) / Close(December)
Close is Yahoo's split-adjusted price, so any split cancels out in the ratio.

TESTS (12-1 signal; fixed 13 and rule-based 15 universes):
  A) median log market cap of winners, losers and all stocks, and losers minus all
     (Newey-West t), like Table D2;
  B) monthly cross-sectional regressions (Fama-MacBeth): for every month t,
        next-month return = a + b1 x loser dummy + b2 x log(size) + b3 x log(Amihud) + error
     across the ranked stocks; the monthly b's are averaged and tested with Newey-West t.
     Version 2 adds a winner dummy. If b1 stays negative and significant with size and
     illiquidity in the regression, the loser effect is not just a small or illiquid-stock effect.
Saves size_tests.xlsx.
"""
import numpy as np
import pandas as pd

from common import MAIN, K_MAIN, load_pool, fixed_universe, rule_based_universe, mean_test, stars
from portfolios import number_per_side
from loser_characteristics import monthly_amihud


def monthly_size(ticker, caps):
    """Market cap (lei) at the end of each month, rolled forward from the previous year-end."""
    daily = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'])
    daily = daily[daily['Volume'] > 0]
    close = daily.groupby(daily['Date'].dt.to_period('M'))['Close'].last()
    december = close[close.index.month == 12]
    size = {}
    for month, price in close.items():
        prev_year = month.year - 1
        cap = caps.get((ticker, prev_year))
        dec = december.get(pd.Period(f'{prev_year}-12', 'M'))
        if cap is not None and dec is not None and dec > 0:
            size[month] = cap * price / dec
    return pd.Series(size, dtype=float)


def fama_macbeth(stocks, log_size, log_amihud, with_winner_dummy):
    signals = pd.DataFrame({t: m[MAIN] for t, m in stocks.items()})
    next_ret = pd.DataFrame({t: m['next_1m'] for t, m in stocks.items()})
    names = ['const', 'loser'] + (['winner'] if with_winner_dummy else []) + ['log_size', 'log_amihud']
    coefs = {}
    for month in signals.index:
        ranked = signals.loc[month].dropna().sort_values()
        n = number_per_side(len(ranked))
        if len(ranked) < 2 * n or next_ret.loc[month].isna().all():
            continue
        df = pd.DataFrame({'y': next_ret.loc[month, ranked.index],
                           'loser': ranked.index.isin(ranked.index[:n]).astype(float),
                           'winner': ranked.index.isin(ranked.index[-n:]).astype(float),
                           'log_size': log_size.reindex(columns=ranked.index).loc[month] if month in log_size.index else np.nan,
                           'log_amihud': log_amihud.reindex(columns=ranked.index).loc[month] if month in log_amihud.index else np.nan},
                          index=ranked.index).dropna()
        if len(df) < len(names) + 3:            # too few stocks with all data this month
            continue
        X = np.column_stack([np.ones(len(df))] + [df[c].values for c in names[1:]])
        b = np.linalg.lstsq(X, df['y'].values, rcond=None)[0]
        coefs[month] = dict(zip(names, b))
    coefs = pd.DataFrame(coefs).T
    rows = []
    for name in names[1:]:
        mean, t, p = mean_test(coefs[name])
        rows.append(dict(variable=name, average_coefficient=mean,
                         annualized=mean * 12 if name in ('loser', 'winner') else np.nan,
                         t_NW=t, p=p, sig=stars(p), months=len(coefs)))
    return pd.DataFrame(rows)


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    caps_table = pd.read_csv('market_cap.csv')
    column = 'market_cap_ron' if 'market_cap_ron' in caps_table.columns else 'market_cap_lei'
    caps_table = caps_table.dropna(subset=[column])
    caps = {(r.ticker, int(r.year)): float(getattr(r, column)) for r in caps_table.itertuples()}

    index_m, pool = load_pool()
    sizes = {t: monthly_size(t, caps) for t in pool}
    log_size = np.log(pd.DataFrame(sizes))
    log_amihud = np.log(pd.DataFrame({t: monthly_amihud(t) for t in pool}).replace(0, np.nan))
    print(f'Market cap available for {sum(len(s) > 0 for s in sizes.values())} of {len(pool)} stocks')

    A, B = [], []
    for universe, stocks in [('Fixed 13', fixed_universe(pool)), (f'Rule-based {K_MAIN}', rule_based_universe(pool))]:
        signals = pd.DataFrame({t: m[MAIN] for t, m in stocks.items()})
        groups = {}
        for month in signals.index:
            ranked = signals.loc[month].dropna().sort_values()
            n = number_per_side(len(ranked))
            if len(ranked) >= 2 * n and month in log_size.index:
                row = log_size.loc[month]
                groups[month] = dict(winners=row.reindex(ranked.index[-n:]).median(),
                                     losers=row.reindex(ranked.index[:n]).median(),
                                     all=row.reindex(ranked.index).median())
        g = pd.DataFrame(groups).T.dropna()
        mean, t, p = mean_test(g['losers'] - g['all'])
        A.append(dict(universe=universe, median_log_size_winners=g['winners'].mean(),
                      median_log_size_losers=g['losers'].mean(), median_log_size_all=g['all'].mean(),
                      losers_minus_all=mean, t_NW=t, p=p, sig=stars(p), months=len(g),
                      losers_size_as_share_of_all=np.exp(mean)))
        for version, winner in [('loser dummy + size + illiquidity', False),
                                ('loser and winner dummies + size + illiquidity', True)]:
            res = fama_macbeth(stocks, log_size, log_amihud, winner)
            res.insert(0, 'model', version)
            res.insert(0, 'universe', universe)
            B.append(res)
    A, B = pd.DataFrame(A), pd.concat(B, ignore_index=True)
    print('\n=== A) Size of winners, losers and all stocks (log market cap, monthly medians) ===')
    print(A.round(4).to_string(index=False))
    print('\n=== B) Monthly cross-sectional regressions of next-month returns (Fama-MacBeth) ===')
    print(B.round(4).to_string(index=False))
    with pd.ExcelWriter('size_tests.xlsx') as xw:
        A.to_excel(xw, sheet_name='A_size_by_group', index=False)
        B.to_excel(xw, sheet_name='B_fama_macbeth', index=False)
    print('\nSaved size_tests.xlsx')
