"""Customer stress keeps paired draws without caching portfolio-sized tensors."""

import tracemalloc

import numpy as np
import pandas as pd
import pytest

from agent1.adaptive.cash_adapter import PartialModel, iter_cash_paths


def inputs(customers, horizon=13):
    frame = pd.DataFrame(dict(
        invoice_id=[str(i) for i in range(len(customers))], customer_id=customers,
        age_days=20, term_days=30, received_fraction=0,
    ))
    distribution = np.full((len(frame), horizon + 1), 1 / (horizon + 1))
    partial = PartialModel(
        np.full(6, .4), tuple(np.array([.25, .6]) for _ in range(6)),
        tuple(np.array([.3, .7]) for _ in range(6)), "2024-01-01", {},
    )
    return frame, distribution, partial


@pytest.mark.parametrize("bit_generator", [np.random.PCG64, np.random.MT19937, np.random.Philox])
def test_nonadjacent_customer_invoices_share_paths_and_preserve_rng_position(bit_generator):
    customers = ["A", "B", "A", "C", "B"]
    frame, distribution, partial = inputs(customers)
    rng = np.random.Generator(bit_generator(19))
    reference = np.random.Generator(bit_generator(19))
    paths, horizon = 500, distribution.shape[1] - 1
    invoices = list(iter_cash_paths(
        distribution, frame, partial, np.full(len(frame), 100.), rng, paths,
        shared_customer=True,
    ))
    for left, right in ((0, 2), (1, 4)):
        np.testing.assert_array_equal(invoices[left].receipts, invoices[right].receipts)
        np.testing.assert_array_equal(invoices[left].remaining, invoices[right].remaining)
        np.testing.assert_array_equal(invoices[left].settlement_week, invoices[right].settlement_week)
    assert not np.array_equal(invoices[0].receipts, invoices[1].receipts)
    # Repeated customers consume no new parent draws, as in the original engine.
    for _ in set(customers):
        reference.random((3, paths, horizon))
    np.testing.assert_array_equal(rng.random(20), reference.random(20))


def test_customer_stress_has_bounded_working_memory_for_a_large_book():
    frame, distribution, partial = inputs([str(i) for i in range(120)])
    rng = np.random.default_rng(7)
    amounts = np.full(len(frame), 100.)
    tracemalloc.start()
    try:
        for invoice in iter_cash_paths(
            distribution, frame, partial, amounts, rng, 1000, shared_customer=True,
        ):
            assert invoice.receipts.shape == (1000, 13)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Old customer tensor caching needs over 36 MiB for this same small book.
    assert peak < 4 * 1024**2, f"Customer stress used {peak / 1024**2:.2f} MiB"
