"""Describe retained components; this is not the v2.1 scoring pipeline."""
import json
from .ml_estimators import catalog


def capabilities():
    return dict(spec_version='2.1',milestone='R2_partial',mode='snapshot_analysis',pipeline_ready=False,
        components=dict(rules=['rules','payment_evidence','authority_policy','batch_controls'],
            statistics=['benford','dynamic_thresholds','threshold_sources','score_statistics','unsupervised_statistics'],
            graph=['identity_graph','entity_graph'],ml=catalog()),
        score_meaning='Rule points, tail statistics, empirical ranks and anomaly scores are not calibrated fraud probabilities.',
        labels_required_for_retained_ml=False,fit_required=True,
        availability_contract='Four-branch snapshot analysis/1.1.0 with read-only scoped artifacts; canonical rules remain incomplete',active_delivery=False,
        validation_api='/api/v1/companies/{company_id}/imports/validate',
        snapshot_api='/api/v1/companies/{company_id}/imports/upload -> preview -> commit -> snapshots',
        analysis_api='POST /api/v1/companies/{company_id}/snapshots/{snapshot_id}/analyze; review allowlist, technical director only',
        feature_job='python -m sme_fraud.feature_pipeline; snapshot_features.py defines the separate ordered feature contract',
        business_pipeline='R1 JSON import/snapshot/features; R2 fit/store/CLI and four-branch HTTP analysis with pinned per-company inference; scoped JSON import workbench implemented. Portal shared-workspace session and scoped membership bridge implemented; named users, CSV/Excel, manager UI, other evaluators/full benchmark/active queue pending')


if __name__=='__main__':print(json.dumps(capabilities(),ensure_ascii=False,indent=2))
