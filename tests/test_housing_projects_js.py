"""The page recomputes the project's money numbers in JavaScript while the growth slider moves.
This runs that JS (the block between the MONA-CALC markers in Base_template.html) under node and
checks it gives the same numbers as src_utils/housing_projects.py, so the housing page and the
accounts page can never disagree. Skipped when node is not installed."""
import json
import os
import re
import shutil
import subprocess

import pytest

import src_utils.housing_projects as hp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, 'source', 'html', 'Base_template.html')

pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')


def _calc_block():
    with open(TEMPLATE, encoding='utf-8') as f:
        m = re.search(r'/\* MONA-CALC-BEGIN \*/(.*?)/\* MONA-CALC-END \*/', f.read(), re.S)
    assert m, 'MONA-CALC markers not found in Base_template.html'
    return m.group(1)


def _run_js(cases, tmp_path):
    script = _calc_block() + """
    const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
    console.log(JSON.stringify(cases.map(c => ({
      sums: monaSums(c.txs),
      derive: monaDerive(c.inp, c.g),
      mortgage: monaExpectedMortgage(c.inp.price, c.down, c.inp.paid_price),
    }))));
    """
    path = tmp_path / 'mona_calc.js'
    path.write_text(script, encoding='utf-8')
    out = subprocess.run(['node', str(path)], input=json.dumps(cases), capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _tx(kind, out=0.0, income=0.0):
    return {'kind': kind, 'out': out, 'income': income}


TXS = [
    [],
    [_tx('price', 15_000), _tx('cost', 5_000)],
    [_tx('price', 150_000), _tx('price', 70_000), _tx('cost', 12_500.5), _tx('income', income=4_000),
     _tx('refund', income=20_000), _tx('income', income=2_800)],
    [_tx('cost', 9_000)],
]
INPUTS = [
    {'price': None, 'years_now': 0.5, 'years_delivery': None, 'years_invested': None},
    {'price': 1_000_000, 'years_now': 0.0, 'years_delivery': 2.0, 'years_invested': 0.1},
    {'price': 1_450_000, 'years_now': 1.37, 'years_delivery': 3.2, 'years_invested': 1.37},
    {'price': 2_100_000, 'years_now': 4.0, 'years_delivery': None, 'years_invested': 0.25},
]


def _cases():
    out = []
    for txs in TXS:
        for base in INPUTS:
            for g in (0, 3, 7.5, 15):
                for down in (25, 40):   # own funds as % of the price (100 − mortgage share)
                    s = hp.sums([{**t, 'income': t['income'], 'out': t['out']} for t in txs])
                    inp = {**base, **{k: s[k] for k in ('paid_price', 'extra_costs', 'income_total', 'net_invested')},
                           'expected_mortgage': hp.expected_mortgage(base['price'], down, s['paid_price'])}
                    if base['years_invested'] is not None and not txs:
                        inp['years_invested'] = None
                    out.append({'txs': txs, 'inp': inp, 'g': g, 'down': down})
    return out


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def test_js_formulas_match_the_python_ones(tmp_path):
    cases = _cases()
    results = _run_js(cases, tmp_path)
    assert len(results) == len(cases) > 100
    for c, r in zip(cases, results):
        s = hp.sums(c['txs'])
        for k, v in s.items():
            assert _close(v, r['sums'][k]), (k, v, r['sums'][k], c)
        d = hp.derive(c['inp'], c['g'])
        for k, v in d.items():
            assert _close(v, r['derive'][k]), (k, v, r['derive'][k], c)
        assert _close(hp.expected_mortgage(c['inp']['price'], c['down'], c['inp']['paid_price']), r['mortgage'])
