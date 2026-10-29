from datetime import date
from itertools import combinations

import pytest

from app import generator

AS_OF = date(2026, 10, 28)


def test_invoice_row_count_is_exactly_n():
    assert len(generator.generate(n=2000, seed=1, as_of=AS_OF)["invoices"]) == 2000


def test_same_seed_gives_identical_data():
    a = generator.generate(n=1000, seed=3, as_of=AS_OF)
    b = generator.generate(n=1000, seed=3, as_of=AS_OF)
    assert a["invoices"].equals(b["invoices"]) and a["truth"] == b["truth"]


def test_different_seed_gives_different_data():
    a = generator.generate(n=1000, seed=3, as_of=AS_OF)
    b = generator.generate(n=1000, seed=4, as_of=AS_OF)
    assert not a["invoices"].equals(b["invoices"])


def test_every_rule_has_the_same_injected_count():
    truth = generator.generate(n=2000, seed=1, as_of=AS_OF)["truth"]
    assert len(truth) == 12
    assert {len(v) for v in truth.values()} == {10}  # 0.5% of 2000


def test_invoice_level_anomaly_blocks_are_disjoint():
    truth = generator.generate(n=2000, seed=1, as_of=AS_OF)["truth"]
    for a, b in combinations(generator.INVOICE_RULES, 2):
        assert not set(truth[a]) & set(truth[b])


def test_too_small_n_raises():
    with pytest.raises(ValueError):
        generator.generate(n=10, seed=1, as_of=AS_OF)


def test_write_csvs_creates_all_files(tmp_path):
    data = generator.generate(n=1000, seed=1, as_of=AS_OF)
    generator.write_csvs(data, str(tmp_path))
    names = {p.name for p in tmp_path.iterdir()}
    assert {"invoices.csv", "payments.csv", "vendors.csv", "customers.csv", "tax_rates.csv", "truth.json"} <= names
