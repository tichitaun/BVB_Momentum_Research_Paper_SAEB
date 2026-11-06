"""
market_cap_proxy.py - build market_cap.csv (needed by size_tests.py) without collecting
hundreds of historical numbers by hand.

THE PROXY
    market cap at the end of year y  ~  current number of shares  x  Yahoo Close at the end of year y
Yahoo's Close is adjusted for splits and bonus issues, so (adjusted old price x current shares)
equals (actual old price x shares at that time) whenever the number of shares changed only
through splits or bonus issues. If a company issued new shares for cash or bought shares back,
the proxy is only approximate. For the size test this is acceptable, because what matters is
the ranking of companies by size, and BVB companies differ in size by a factor of up to 100.

WHERE THE NUMBER OF SHARES COMES FROM
  1. shares_outstanding.csv (columns ticker,shares_outstanding,source), if you create it:
     values typed from the BVB issuer pages always take priority;
  2. otherwise Yahoo Finance (yfinance, field sharesOutstanding of TICKER.RO).
Stocks with no number from either source are listed at the end; add them to
shares_outstanding.csv and run the script again.

Writes market_cap.csv (ticker, year, market_cap_lei, source) and shares_used.csv.
"""
import os

import pandas as pd

from common import ALL_STOCKS

YEARS = range(2014, 2025)          # year-ends used by size_tests.py (2014 is needed for 2015)


def shares_from_file():
    if not os.path.exists('shares_outstanding.csv'):
        return {}
    df = pd.read_csv('shares_outstanding.csv')
    return {r.ticker.strip().upper(): (float(r.shares_outstanding), str(getattr(r, 'source', 'manual')))
            for r in df.itertuples() if pd.notna(r.shares_outstanding)}


def shares_from_yahoo(ticker):
    try:
        import yfinance as yf
        info = yf.Ticker(f'{ticker}.RO').info
        value = info.get('sharesOutstanding') or info.get('impliedSharesOutstanding')
        return float(value) if value else None
    except Exception as error:
        print(f'{ticker}: Yahoo lookup failed ({error})')
        return None


if __name__ == '__main__':
    manual = shares_from_file()
    rows, used, missing = [], [], []
    for ticker in ALL_STOCKS:
        if ticker in manual:
            shares, source = manual[ticker]
        else:
            shares, source = shares_from_yahoo(ticker), 'Yahoo Finance sharesOutstanding'
        if not shares:
            missing.append(ticker)
            continue
        used.append(dict(ticker=ticker, shares_outstanding=shares, source=source))

        daily = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'])
        daily = daily[daily['Volume'] > 0]
        for year in YEARS:
            in_year = daily[daily['Date'].dt.year == year]
            if in_year.empty:
                continue                      # not yet listed
            close = in_year.iloc[-1]['Close']  # last trading day of the year, split-adjusted
            rows.append(dict(ticker=ticker, year=year, market_cap_lei=shares * close,
                             source=f'proxy: {source} x Yahoo Close'))

    pd.DataFrame(rows).to_csv('market_cap.csv', index=False)
    pd.DataFrame(used).to_csv('shares_used.csv', index=False)

    caps = pd.DataFrame(rows)
    print(f'Shares found for {len(used)} of {len(ALL_STOCKS)} stocks; market_cap.csv has {len(caps)} rows')
    latest = caps[caps['year'] == 2024].sort_values('market_cap_lei', ascending=False)
    print('\nProxy market cap at the end of 2024 (billion lei) - check that these look plausible:')
    for r in latest.itertuples():
        print(f'  {r.ticker:6s}{r.market_cap_lei / 1e9:10.2f}')
    if missing:
        print('\nNo number of shares for:', ', '.join(missing))
        print('Add them to shares_outstanding.csv (ticker,shares_outstanding,source) and run again.')
    print('\nSaved market_cap.csv and shares_used.csv. Next: python size_tests.py')
