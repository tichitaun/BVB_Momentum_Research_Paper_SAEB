"""
run_all.py - run the whole analysis, in order, with one command:

    python run_all.py

The data must already be in this folder (download_pool.py + the BET-TR file), and the
cross-market data in markets/data (markets/markets_download.py). Downloading is not part of
this script, so that a rerun always uses exactly the same data.
Every script's output is printed and also saved to run_all_log.txt.
The run stops at the first error.
"""
import glob
import os
import subprocess
import sys
import time

# always work in the folder where this file is saved, wherever it is started from
os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f'Working folder: {os.getcwd()}')

SCRIPTS = [
    # --- data records and checks (run first)
    'make_manifest.py',          # record the input files (dates, rows, hashes) and package versions
    'data_audit.py',             # Table B1: dividend adjustments, spikes, every daily move above 40%
    'check_market_cap.py',       # compare the BVB year-end market caps with Yahoo's price changes
    'checks.py',                 # 8 timing and accounting tests (must all pass)
    # --- main results
    'table1.py',                 # Table 1: summary statistics
    'analysis.py',               # Tables 2-3: predictive regressions, panel, winners minus losers
    'robustness.py',             # Table 4, Figure 1: sector-neutral, leave-one-out, sub-periods, alpha
    'long_only.py',              # Table 5: long-only portfolios, cost levels
    'concentration.py',          # Table 5: Top 1-4 portfolios
    'universe.py',               # Tables 3, 5, A1: rule-based universe
    'walk_forward.py',           # Section 6.4 (text only): exploratory walk-forward test
    'costs.py',                  # Sections 5.7 and 6.4 (text): stock-specific costs and capacity
    'losers.py',                 # Table 6, Figure 2: winners vs losers, avoid-losers portfolio
    'extra_tests.py',            # Tables 4 and 6: leg difference, rule-based robustness, market states
    'pool_rule.py',              # Table 4, Section 6.3: pool defined by the BET-XT rule
    # --- appendix
    'sensitivity.py',            # Table B2: results with and without the manual corrections
    'inference.py',              # Table C1: Newey-West lags, confidence intervals, bootstrap
    'loser_characteristics.py',  # Table C2: liquidity, volatility, beta and sectors of the losers
    'size_tests.py',             # Table C3: size, illiquidity and the loser effect
    'charts_1000_lei.py',        # growth-of-1,000-lei charts (supplementary)
]
# input files that some scripts need besides the stock prices
EXTRA_INPUTS = ['market_cap.csv',               # check_market_cap.py, size_tests.py
                'bvb_regulated_shares.csv']     # pool_rule.py
MODULES = ['common.py', 'portfolios.py']    # shared code imported by the scripts

# ---- check that everything needed is in this folder before starting
missing = [f for f in SCRIPTS + MODULES + EXTRA_INPUTS if not os.path.exists(f)]
if not os.path.exists('Bucharest_Total_Return_Historical_Data.xlsx'):
    missing.append('Bucharest_Total_Return_Historical_Data.xlsx')
n_csv = len(glob.glob('*_historical_data.csv'))
if n_csv < 13:
    missing.append(f'stock CSV files (found only {n_csv}, expected about 32)')
if missing:
    print('Run this from the folder that contains ALL scripts and ALL data. Missing here:')
    for f in missing:
        print('   -', f)
    sys.exit(1)

# ---- run every script in order
with open('run_all_log.txt', 'w', encoding='utf-8') as log:
    for script in SCRIPTS:
        start = time.time()
        header = f'\n{"=" * 80}\nRUNNING {script}\n{"=" * 80}\n'
        print(header, flush=True)
        log.write(header)

        # a script in a subfolder (markets/...) is run from inside that folder
        folder, name = os.path.split(script)
        result = subprocess.run([sys.executable, name], capture_output=True, text=True, cwd=folder or None)
        print(result.stdout)
        log.write(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            log.write(result.stderr)
            print(f'\nSTOPPED: {script} failed. Send me the error above.')
            sys.exit(1)
        print(f'{script} finished in {time.time() - start:.0f} s', flush=True)

print('\nAll scripts finished. Full output saved to run_all_log.txt')