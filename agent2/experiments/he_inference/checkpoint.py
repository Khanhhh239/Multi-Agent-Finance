"""Strict JSON checkpoint; serialized private HE context only inside node AEAD."""
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version as _pkg_version
import hashlib
from pathlib import Path

try:
    import tenseal as ts
except ImportError:  # pragma: no cover - optional wheel on Windows Python 3.12+
    ts = None


def version(pkg_name: str) -> str:
    try:
        return _pkg_version(pkg_name)
    except PackageNotFoundError:
        return getattr(ts, '__version__', '0.3.18')

from .enterprise import EnterpriseSession
from .protocol import BINDING, HEUnavailable, b64, unb64, MAX_CONTEXT, require
from .registry_export import RegistryExport
import experiments.he_inference.registry_export as registry

VERSION = 'he-private-checkpoint/1.0.0'


def _require_tenseal():
    if ts is None:
        raise HEUnavailable('tenseal_unavailable')
    return ts


def freeze(export):
    _require_tenseal()
    export._check()
    require(export.ready, 'HE_EXPORT_UNAVAILABLE')
    return dict(version=VERSION, tenseal_version=version('tenseal'),
                rows=deepcopy(export.rows), receipt=deepcopy(export.receipt), positions=list(export._positions),
                packet=deepcopy(export._packet), policy=deepcopy(export._policy),
                worker_verify_key=export._session.pending[export._packet['payload']['nonce']]['worker_verify_key'],
                private_context=b64(export._session.context.serialize(save_secret_key=True, save_public_key=False,
                                    save_relin_keys=False, save_galois_keys=False)))


def restore(value, check, scope, worker_verify_key):
    ts_mod = _require_tenseal()
    check()
    require(isinstance(value, dict) and set(value) == {'version', 'tenseal_version', 'rows', 'receipt', 'positions',
                'packet', 'policy', 'worker_verify_key', 'private_context'}, 'CHECKPOINT_INVALID')
    require(value['version'] == VERSION and value['tenseal_version'] == version('tenseal'), 'CHECKPOINT_INCOMPATIBLE')
    require(value['worker_verify_key'] == worker_verify_key, 'CHECKPOINT_WORKER_KEY_CHANGED')
    receipt = value['receipt']; packet = value['packet']; p = packet['payload']
    require((receipt['tenant_id'], receipt['company_id']) == (scope.tenant_id, next(iter(scope.company_ids)))
            == (p['tenant_id'], p['company_id']), 'CHECKPOINT_SCOPE')
    require(receipt['exporter_sha256'] == hashlib.sha256(Path(registry.__file__).read_bytes()).hexdigest(), 'CHECKPOINT_INCOMPATIBLE')
    require(p['model_id'] == receipt['opaque_model_id']
            and all(p[k] == value['policy'][k] for k in BINDING), 'CHECKPOINT_BINDING')
    session = EnterpriseSession.__new__(EnterpriseSession)
    session.context = ts_mod.context_from(unb64(value['private_context'], MAX_CONTEXT), n_threads=1)
    require(session.context.has_secret_key(), 'CHECKPOINT_KEY_MISSING')
    session.binding = {k: p[k] for k in BINDING}
    session.pending = {p['nonce']: dict(request=deepcopy(packet), worker_verify_key=worker_verify_key)}
    require(len(value['positions']) == len(p['row_handles'])
            and all(type(i) is int and 0 <= i < len(value['rows']) for i in value['positions'])
            and len(set(value['positions'])) == len(value['positions']), 'CHECKPOINT_ROWS')
    check()
    return RegistryExport(deepcopy(value['rows']), deepcopy(receipt), check, session=session,
                          packet=deepcopy(packet), policy=deepcopy(value['policy']), positions=value['positions'])
