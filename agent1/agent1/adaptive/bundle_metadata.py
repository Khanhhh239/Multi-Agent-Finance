"""Identity of serving parameters, kept separate from later update attempts."""

import hashlib
import json
import pickle


def component_timing(bundle, name):
    """Use explicit dates, or a conservative upper bound for older bundles."""
    component = bundle.get(name) or {}
    legacy = max((bundle.get(k) for k in ("asof", "update_asof") if bundle.get(k)), default=None)
    fitted = component.get("fitted_through")
    ready = component.get("ready_on")
    return dict(fitted_through=fitted or legacy, ready_on=ready or fitted or legacy,
                source="component" if fitted and ready else "legacy_bundle_upper_bound")


def serving_mode(bundle):
    """Describe actual serving parameters, independent of registry existence."""
    provenance = bundle.get("t1_provenance") or {}
    version = str(bundle.get("t1_version") or "")
    if (version.startswith("global:")
            or not version and provenance.get("source") == "global_catalog"):
        return "global_fallback"
    evidence = getattr(bundle.get("partial"), "evidence", {})
    local_partial = bool(evidence.get("prior_sha256")) and any(
        cell.get("weeks", 0) > 0 for cell in evidence.get("cells", [])
    )
    method = bundle.get("serving_method", "")
    local_t1 = "local" in method
    global_t1 = method.startswith("global_")
    if local_t1 and "_a" in method:
        try:
            alpha = float(method.rsplit("_a", 1)[1])
            local_t1, global_t1 = alpha > 0, alpha == 0
        except ValueError:
            local_t1 = False
    if local_partial or local_t1:
        return "company_adapted"
    if global_t1:
        return "global_selected"
    return "saved_model"


def serving_manifest(bundle, *, data_version, policy, ready_on):
    policy_json = json.dumps(policy, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return dict(
        t1_version=bundle["t1_version"],
        t1_model_sha256=hashlib.sha256(pickle.dumps(bundle["model"], protocol=4)).hexdigest(),
        adapter_version=bundle["adapter_version"],
        partial_version=bundle["partial"].digest,
        data_version=data_version,
        policy=json.loads(policy_json),
        policy_version=hashlib.sha256(policy_json.encode()).hexdigest(),
        ready_on=ready_on,
        t1_parameter_asof=bundle.get("t1_parameter_asof"),
        partial_fitted_through=bundle["partial"].fitted_through,
        auxiliary_timing={name: component_timing(bundle, name)
                          for name in ("risk", "operating") if bundle.get(name)},
    )
