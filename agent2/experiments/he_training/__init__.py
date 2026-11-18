"""Opt-in supervised FHE training & cross-enterprise encrypted consortium SGD."""

VERSION = 'encrypted-supervised-training/0.1.0'
TARGET = 'verified-fraud/1.0.0'

PROFILE_VERSION = 'fhe_sgd_s16_v2'
LEGACY_PROFILE_VERSION = 'legacy_s2_v1'
LEGACY_PROFILE = 'experimental-quantized-logistic-sgd-2d/0.1.0'
PROFILE = PROFILE_VERSION

EXECUTION_MODE_NATIVE = 'fhe_concrete_native'
EXECUTION_MODE_VERIFIED = 'fhe_quantized_circuit_verified'

QUANTIZATION_PROFILES = {
    PROFILE_VERSION: dict(
        profile_version=PROFILE_VERSION,
        profile_id=PROFILE_VERSION,
        weight_scale=16,
        bias_scale=16,
        probability_scale=16,
        feature_scale=1,
        learning_rate=1,
        effective_float_learning_rate=1.0,
        batch_size=4,
        features=2,
        input_domain=[0, 1],
        label_domain=[0, 1],
        weight_domain=[-16, 16],
        bias_domain=[-32, 32],
        logit_domain=[-64, 64],
        gradient_sum_domain=[-64, 64],
        pre_clip_weight_domain=[-32, 32],
        pre_clip_bias_domain=[-48, 48],
        rounding='half_away_from_zero',
        lut_sizes=dict(sigmoid=129, round_div4=129, clip_w=65, clip_b=97),
    ),
    LEGACY_PROFILE_VERSION: dict(
        profile_version=LEGACY_PROFILE_VERSION,
        profile_id=LEGACY_PROFILE,
        weight_scale=2,
        bias_scale=2,
        probability_scale=4,
        feature_scale=1,
        learning_rate=1,
        effective_float_learning_rate=0.5,
        batch_size=4,
        features=2,
        input_domain=[-1, 1],
        label_domain=[0, 1],
        weight_domain=[-2, 2],
        bias_domain=[-4, 4],
        logit_domain=[-8, 8],
        gradient_sum_domain=[-32, 32],
        pre_clip_weight_domain=[-6, 6],
        pre_clip_bias_domain=[-8, 8],
        rounding='round_to_even',
        lut_sizes=dict(sigmoid=32, round_div8=64, clip_w=16, clip_b=16),
    ),
}

PROFILE_ALIASES = {
    PROFILE_VERSION: PROFILE_VERSION,
    'quantized-logistic-sgd-2d-s16/0.2.0': PROFILE_VERSION,
    LEGACY_PROFILE_VERSION: LEGACY_PROFILE_VERSION,
    LEGACY_PROFILE: LEGACY_PROFILE_VERSION,
}
SUPPORTED_PROFILES = frozenset(PROFILE_ALIASES.keys())


def resolve_quantization_profile(spec=None) -> dict:
    """Resolve quantization profile metadata; never silently decode legacy scale=2 as scale=16."""
    if spec is None:
        return dict(QUANTIZATION_PROFILES[PROFILE_VERSION])
    if isinstance(spec, str):
        canonical_name = PROFILE_ALIASES.get(spec)
        if canonical_name is None:
            raise ValueError(f'UNKNOWN_QUANTIZATION_PROFILE:{spec}')
        return dict(QUANTIZATION_PROFILES[canonical_name])
    if isinstance(spec, dict):
        explicit = spec.get('profile_version') or spec.get('profile')
        if explicit in PROFILE_ALIASES:
            resolved = dict(QUANTIZATION_PROFILES[PROFILE_ALIASES[explicit]])
            w_scale = spec.get('weight_scale')
            if w_scale is not None and int(w_scale) != resolved['weight_scale']:
                raise ValueError('QUANTIZATION_SCALE_PROFILE_MISMATCH')
            return resolved
        w_scale = spec.get('weight_scale')
        p_scale = spec.get('probability_scale')
        if w_scale == 16 and (p_scale in (None, 16)):
            return dict(QUANTIZATION_PROFILES[PROFILE_VERSION])
        if w_scale == 2 and (p_scale in (None, 4)):
            return dict(QUANTIZATION_PROFILES[LEGACY_PROFILE_VERSION])
    raise ValueError('UNKNOWN_QUANTIZATION_PROFILE')
