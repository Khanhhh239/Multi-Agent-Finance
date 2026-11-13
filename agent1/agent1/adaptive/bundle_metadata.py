"""Identity of serving parameters, kept separate from later update attempts."""

import hashlib
import json
import pickle


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
    )
