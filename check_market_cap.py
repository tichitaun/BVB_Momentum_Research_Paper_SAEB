"""
check_market_cap.py - check the hand-collected year-end market caps (market_cap.csv).

From one year-end to the next, a company's market cap changes because
  (a) its price changes, and (b) its number of shares changes.
Yahoo's Close is adjusted for splits and bonus issues, so
    implied share change = (cap this year / cap last year) / (Close this year / Close last year)
is about 1 unless the company issued new shares for cash, bought shares back, or a value
was typed wrongly. Every year where the implied change is more than 20% away from 1 is
listed, so you can look at the BVB December report again.

Reads market_cap.csv (column market_cap_ron or market_cap_lei) and the stock CSV files.
Prints the suspicious cases and saves market_cap_check.csv.
"""
import os

import pandas as pd

caps = pd.read_csv('market_cap.csv')
column = 'market_cap_ron' if 'market_cap_ron' in caps.columns else 'market_cap_lei'
caps = caps.dropna(subset=[column]).sort_values(['ticker', 'year'])

rows = []
for ticker, g in caps.groupby('ticker'):
    path = f'{ticker}_historical_data.csv'
    if not os.path.exists(path):
        continue
    daily = pd.read_csv(path, parse_dates=['Date'])
    daily = daily[daily['Volume'] > 0]
    year_end_close = daily.groupby(daily['Date'].dt.year)['Close'].last()
    g = g.set_index('year')[column]
    for year in g.index:
        if year - 1 not in g.index or year not in year_end_close.index or year - 1 not in year_end_close.index:
            continue
        cap_ratio = g[year] / g[year - 1]
        price_ratio = year_end_close[year] / year_end_close[year - 1]
        implied = cap_ratio / price_ratio
        rows.append(dict(ticker=ticker, year=year, cap_ratio=cap_ratio, price_ratio=price_ratio,
                         implied_share_change=implied, suspicious=abs(implied - 1) > 0.20))

check = pd.DataFrame(rows)
check.to_csv('market_cap_check.csv', index=False)
flagged = check[check['suspicious']]
print(f'{len(check)} year-to-year changes checked; {len(flagged)} look suspicious '
      f'(share count would have changed by more than 20%):\n')
print(flagged.round(3).to_string(index=False) if len(flagged) else 'none')
print('\nFor each case: open the BVB December report for that year and the year before, and check '
      'the value. If both values are right, the company really issued or cancelled shares; that is fine.')
