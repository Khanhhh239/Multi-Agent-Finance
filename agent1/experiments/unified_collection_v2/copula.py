"""Conditional copula factors used by the corrected v2 rollout."""
import numpy as np
from scipy.special import ndtr


def conditional_uniforms(rng, n, firm_codes, customer_codes, rho_firm, rho_customer):
    if rho_firm < 0 or rho_customer < 0 or rho_firm+rho_customer > 1:
        raise ValueError("Invalid conditional copula variance")
    m = len(firm_codes)
    latent = np.sqrt(1-rho_firm-rho_customer)*rng.standard_normal((n, m))
    if rho_firm:
        latent += np.sqrt(rho_firm)*rng.standard_normal((n, int(max(firm_codes, default=-1))+1))[:, firm_codes]
    if rho_customer:
        latent += np.sqrt(rho_customer)*rng.standard_normal((n, int(max(customer_codes, default=-1))+1))[:, customer_codes]
    return ndtr(latent)
