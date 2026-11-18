"""Operator-only batch commands. Labels remain in the enterprise label vault."""
import os
from .batch_enterprise import BatchEnterprise
from .batch_plan import prepare_batch_plan
from .protocol import require, strict_json
from .runtime import ENV_HE_AGGREGATOR_URL
from .snapshot_adapter import ReadOnlySnapshots


def label_store(cfg):
    from sme_fraud.label_packets import LabelStore
    return LabelStore.from_state_key(cfg['label_db'], cfg['node_state_key_file'])


def execute(args, cfg, scope, check):
    action = args.action
    if action in ('batch-preview', 'batch-prepare', 'batch-create-labels'):
        require(args.data is not None, 'BATCH_REQUEST_REQUIRED')
        snapshots = ReadOnlySnapshots(cfg['snapshot_db'])
        request = strict_json(args.data.read_bytes())
        plan = prepare_batch_plan(snapshots, scope, request, check)
        if action == 'batch-preview':
            return plan
        require(plan['status'] == 'ready', 'BATCH_SNAPSHOT_NOT_READY')
        require(cfg.get('expected_batch_plan_sha256') == plan['plan_sha256'], 'BATCH_PREVIEW_STALE')
        if action == 'batch-create-labels':
            from sme_fraud.label_packets import source_packet
            labels = label_store(cfg)
            rows = []
            for kind in ('training', 'evaluation'):
                for i, part in enumerate(plan['parts'][kind]):
                    packet = labels.create(scope, source_packet(snapshots, scope, part['request'], check), check)
                    rows.append(dict(partition=kind, batch_index=i, packet_id=packet['packet_id'], revision=packet['revision'], locked=packet['locked']))
            return dict(plan_sha256=plan['plan_sha256'], packets=rows, labels_assigned=False, training_started=False)
    node = BatchEnterprise(
        cfg['enterprise_root'],
        cfg['build'],
        scope,
        recheck=check,
        python=cfg.get('linux_python'),
        distro=cfg.get('distro'),
    )
    url = cfg.get('worker_url') or os.environ.get(ENV_HE_AGGREGATOR_URL, '').strip() or None
    pub = cfg.get('worker_verify_key')
    if action == 'batch-prepare':
        source = node.prepare_snapshot_batches(snapshots, request, expected_plan_sha256=cfg['expected_batch_plan_sha256'])
        return dict(dataset_id=source['dataset_id'], plan_sha256=plan['plan_sha256'], uploaded=False)
    if action == 'batch-upload':
        return node.upload_batches(url, pub)
    if action == 'batch-review-template':
        return dict(batches=node.batch_review_templates())
    if action in ('batch-confirm', 'batch-confirm-locked'):
        require(args.labels is not None, 'LABEL_FILE_REQUIRED')
        labels = strict_json(args.labels.read_bytes())
        epochs = cfg.get('batch_epochs', 1)
        if action == 'batch-confirm-locked':
            return node.confirm_locked_batches(url, pub, label_store(cfg), labels, epochs=epochs)
        return node.confirm_batch_reviews(url, pub, labels, epochs=epochs)
    if action in ('batch-run', 'batch-status'):
        return node.access_batches(url, pub, 'run' if action == 'batch-run' else 'status')[0]
    if action == 'batch-receive':
        return node.receive_batches(url, pub)
    if action == 'batch-evaluate':
        locks = strict_json(args.labels.read_bytes()) if args.labels is not None else None
        return node.evaluate_holdout(label_store=label_store(cfg) if locks is not None else None, evaluation_locks=locks)
    if action == 'batch-approve':
        require(args.reason_file is not None, 'REASON_FILE_REQUIRED')
        return node.approve_batches(
            args.reason_file.read_text('utf-8'),
            expected_model_cipher_sha256=cfg.get('expected_model_cipher_sha256'),
            expected_plan_sha256=cfg.get('expected_batch_plan_sha256'),
            expected_evaluation_sha256=cfg.get('expected_evaluation_sha256'),
        )
    if action == 'batch-shadow':
        if args.data is not None:
            data = strict_json(args.data.read_bytes())
            return node.predict_batch_shadow(data['x'], row_ids=data.get('row_ids'), mapping_fingerprint=data.get('mapping_fingerprint'))
        return node.evaluate_shadow_holdout()
    raise ValueError('unknown batch action')
