"""Frozen-reference midranks, not calibrated probabilities of fraud."""
import numpy as np


def empirical_rank(validation, scores):
    reference = np.sort(validation)
    # Mid-rank ties; never use future/test distribution as the reference.
    return (np.searchsorted(reference, scores, side='left') + np.searchsorted(reference, scores, side='right')) / (2 * len(reference))
