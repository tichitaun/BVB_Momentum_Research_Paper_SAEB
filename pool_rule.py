"""
pool_rule.py - replace the hand-picked 32-stock pool with a pool defined by a rule.

THE RULE: every share that
  (1) appears in the list saved as bvb_regulated_shares.csv. The list provided is the
      composition of the BET-XT index (the 30 most traded BVB stocks) in April 2026, from the
      BVB index profile; any other official list with the same columns can be used instead,
  (2) is an ordinary company share (closed-end investment funds such as Fondul Proprietatea
      and the former SIFs are excluded, because they mainly hold other listed shares),
  (3) has Yahoo Finance data (ticker.RO), and
  (4) traded on at least 24 different months between January 2015 and December 2025.

INPUT: bvb_regulated_shares.csv, with three columns (a fourth, source, is optional):
    ticker,name,type
    TLV,Banca Transilvania,share
    FP,Fondul Proprietatea,fund
Write 'share' or 'fund' in the type column.

WHAT IT DOES:
  - downloads from Yahoo every listed share that is not yet in this folder (existing files
    are not changed);
  - applies the rule and prints which stocks enter and leave compared with the 32-stock pool;
  - recomputes the main rule-based results with both pools, side by side.
Saves pool_rule.xlsx. Stock prices of new companies are not checked by hand: any day with a
suspicious dividend adjustment is printed as a WARNING and should be checked before use.
"""
import os

import pandas as pd

import common
from common import MAIN, K_MAIN, BASE_COST, rf_for_holding_month, mean_test, stars, summarize
from portfolios import wml_series, leg_returns, avoid_losers
from losers import alpha_against

START, END = '2015-01-01', '2026-01-01'
MIN_MONTHS = 24


def download_missing(tickers):
    for ticker in tickers:
        path = f'{ticker}_historical_data.csv'
        if os.path.exists(path):
            continue
        import yfinance as yf
        df = yf.download(f'{ticker}.RO', start=START, end=END, auto_adjust=False, progress=False)
        if df is None or df.empty:
            print(f'{ticker}: no Yahoo data')
            continue
        df.columns = df.columns.get_level_values(0)
        df.to_csv(path)
        print(f'{ticker}: downloaded {len(df)} days')


def months_with_trades(ticker):
    path = f'{ticker}_historical_data.csv'
    if not os.path.exists(path):
        return 0
    df = pd.read_csv(path, parse_dates=['Date'])
    traded = df[df['Volume'] > 0]
    return traded['Date'].dt.to_period('M').nunique()


def key_results(pool_tickers, label):
    """Rule-based universe results for a given pool of tickers."""
    saved = list(common.ALL_STOCKS)
    common.ALL_STOCKS[:] = pool_tickers
    try:
        index_m, pool = common.load_pool()
    finally:
        common.ALL_STOCKS[:] = saved
    stocks = common.restrict(pool, common.membership(pool, K_MAIN))
    rows = [{'pool': label, **summarize(wml_series(stocks, MAIN), 'winners - losers')}]
    legs = leg_returns(stocks, MAIN).astype(float)
    for name, x in [('winner leg', legs['winners'] - legs['all']), ('loser leg', legs['all'] - legs['losers'])]:
        rows.append({'pool': label, **summarize(x, name)})
    avoid, everyone = avoid_losers(stocks, MAIN, 'frac'), avoid_losers(stocks, MAIN, 0)
    months = everyone.returns.index
    alpha, t, p = alpha_against((avoid.returns - BASE_COST * avoid.turnover).reindex(months),
                                everyone.returns - BASE_COST * everyone.turnover, rf_for_holding_month(months))
    rows.append(dict(pool=label, test='avoid-losers alpha vs equal weight', annualized=alpha, t_NW=t, p=p,
                     sig=stars(p)))
    ever_in = [t for t, col in common.membership(pool, K_MAIN).items() if col.any()]
    return pd.DataFrame(rows), ever_in


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    official = pd.read_csv('bvb_regulated_shares.csv')
    official['ticker'] = official['ticker'].str.strip().str.upper()
    shares = official[official['type'].str.strip().str.lower() == 'share']['ticker'].tolist()
    print(f'Official list: {len(official)} securities, {len(shares)} ordinary shares')

    download_missing(shares)
    counts = {t: months_with_trades(t) for t in shares}
    rule_pool = [t for t in shares if counts[t] >= MIN_MONTHS]
    old_pool = list(common.ALL_STOCKS)

    entering = sorted(set(rule_pool) - set(old_pool))
    leaving = sorted(set(old_pool) - set(rule_pool))
    print(f'\nRule-based pool: {len(rule_pool)} stocks (old pool: {len(old_pool)})')
    print('Enter the pool:', ', '.join(entering) or 'none')
    print('Leave the pool:', ', '.join(leaving) or 'none')

    old_results, old_ever = key_results(old_pool, 'hand-picked 32')
    new_results, new_ever = key_results(rule_pool, f'rule ({len(rule_pool)} stocks)')
    comparison = pd.concat([old_results, new_results], ignore_index=True)
    print(f'\n=== Rule-based {K_MAIN}-stock universe, 12-1 signal: old pool vs pool defined by the rule ===')
    print(comparison.round(4).to_string(index=False))
    print(f'\nStocks ever in the 15-stock universe: old pool {len(old_ever)}, rule pool {len(new_ever)}; '
          f'only with the rule: {", ".join(sorted(set(new_ever) - set(old_ever))) or "none"}')

    with pd.ExcelWriter('pool_rule.xlsx') as xw:
        pd.DataFrame({'ticker': shares, 'months_with_trades': [counts[t] for t in shares],
                      'in_rule_pool': [t in rule_pool for t in shares],
                      'in_old_pool': [t in old_pool for t in shares]}).to_excel(xw, sheet_name='pool', index=False)
        comparison.to_excel(xw, sheet_name='comparison', index=False)
    print('\nSaved pool_rule.xlsx')
