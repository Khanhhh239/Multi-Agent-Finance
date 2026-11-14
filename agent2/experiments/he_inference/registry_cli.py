"""Enterprise CLI: explicit offline fit, or export and score in a local HE worker.

score-local is an experiment, not a network/cloud service. Credentials remain in
an operator-managed token file and are never forwarded to the ciphertext worker.
"""
import argparse
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from finance_input.json_io import loads

from sme_fraud.auth import AuthError, FileAuthorizer
from sme_fraud.import_files import ImportFailure, fail
from sme_fraud.method_jobs import _write_result
from sme_fraud.method_store import MethodStore, require_fit
from sme_fraud.snapshots import SnapshotStore
from .demo import worker_process
from .protocol import HEUnavailable, public_hex
from .registry_export import export_snapshot
from .registry_fit import run_fit_job


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('fit', 'score-local'))
    for name in ('snapshot-db', 'model-db', 'auth-file', 'token-file', 'company', 'output'):
        parser.add_argument('--' + name, required=True)
    for name in ('config', 'idempotency-key', 'artifact-id', 'snapshot-id', 'as-of'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    try:
        auth = FileAuthorizer(args.auth_file)
        header = 'Bearer ' + Path(args.token_file).read_text('utf-8').strip()
        scope = auth.authorize(header, args.company)
        check = lambda: auth.authorize(header, args.company)
        if args.mode == 'fit':
            require_fit(scope)
            if not args.config or not args.idempotency_key:
                raise ValueError('fit requires --config and --idempotency-key')
            if not Path(args.snapshot_db).is_file():
                fail(404, 'SNAPSHOT_NOT_FOUND', 'Chưa có kho snapshot.', 'Chọn snapshot đã lưu trước khi fit.')
            snapshots = SnapshotStore(args.snapshot_db)
            models = MethodStore(args.model_db)
            result = run_fit_job(snapshots, models, auth, header, args.company,
                                loads(Path(args.config).read_bytes()), args.idempotency_key)
            code = 0
        else:
            if not args.artifact_id or not args.snapshot_id or not args.as_of:
                raise ValueError('score-local requires --artifact-id, --snapshot-id and --as-of')
            signer = Ed25519PrivateKey.generate()
            export = export_snapshot(args.model_db, args.snapshot_db, auth, header, args.company,
                                     args.artifact_id, args.snapshot_id, args.as_of, public_hex(signer))
            if export.ready:
                package = export.cloud_package()
                with tempfile.TemporaryDirectory(prefix='he-registry-cli-') as temporary:
                    response, worker_code, _ = worker_process(package['request'], package['policy'], signer,
                                                             Path(temporary) / 'worker')
                    if worker_code:
                        raise HEUnavailable(response.get('reason', {}).get('code', 'HE_WORKER_UNAVAILABLE'))
                    result = export.open(response)
            else:
                result = export.local_result()
            result['execution'] = 'local_ciphertext_worker_not_cloud_deployment'
            code = 0 if result['status'] in ('available', 'partial') else 2
        _write_result(args.output, result, check, scope)
        print('Đã ghi kết quả local:', Path(args.output).resolve())
        return code
    except (AuthError, ImportFailure) as exc:
        print(exc.code + ': ' + exc.message)
        return 2
    except HEUnavailable as exc:
        print('HE chưa khả dụng: ' + exc.code)
        return 2
    except (ValueError, OSError, TypeError):
        print('HE chưa khả dụng: kiểm tra cấu hình/đường dẫn; không fit trong bước xuất.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
