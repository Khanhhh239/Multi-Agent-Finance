# Agent2 GitHub update - 2026-11-18

Development snapshot on `platform-Khanh`, based on `40ac9b80bae38cbe19fc3369972de049fdf85e8a`. Scope: Agent2, its shared input contract and its Portal integration. Preserve upstream Portal UI and Agent1/3/4. No live Portal deployment or restart in this update.

## Included work

- Multi-source rule intake, signed adjustments and source knowledge timestamps.
- Case workspace with review, evidence and remediation tasks.
- HE execution in the bundle coordinator with snapshot/model/build/key bindings and durable resume; unsupported branches remain unavailable.
- Development extensions for A6/C2 and two-column RobustZ, not yet accepted.
- Agent2 rejected-upload-body handling in Portal; preserve the upstream server and shared UI.

## Checks on the merged publication checkout

- 145 regression tests: **144 pass, 1 error**. Full receipt: `../../Agent2_Spec_v2_1/evidence/R6/github_update_20261118/tests.json`.
- Open error: `test_bundle_he.BundleHETests.test_extended_he_covers_a6_c2_and_2col_robust_z_statistics` reaches the HE run after fitting, then raises `PIPELINE_HE_FAILED` with worker reason `HE4_PIPELINE_INTEGRITY`. Investigate before accepting or deploying the extension.
- Python compile checks for Agent2 backend/HE4 and both edited Portal files pass.
- Staged whitespace and scope checks pass. Runtime databases, models, secret/evaluation keys and test ciphertext are excluded.

Earlier HE reports remain historical evidence for their recorded versions/profiles. They do not prove acceptance of these new extensions, full 35-rule/33-feature HE, fraud-detection effectiveness or production readiness.


## Follow-up after fdb9b9d (2026-11-18)

Latest source updates include HE evidence reference identifiers, C2 adapter behavior, suppression metadata, extended regression scenarios, runtime sync tooling and related documentation. No runtime sync or live deployment is executed by this publication.

Scoped regression rerun: 13/15 pass, 2 failures, 0 errors. Receipt: `../../Agent2_Spec_v2_1/evidence/R6/github_update_20261118/latest_tests.json`. These tests use synthetic circuit transport; they do not certify native FHE performance or full-catalogue support.

Open checks:

- `test_cloud_dispatch_to_common_queue_review_and_replay_no_clear_executor (test_bundle_he.BundleHETests.test_cloud_dispatch_to_common_queue_review_and_replay_no_clear_executor)`
- `test_extended_he_covers_a6_c2_and_2col_robust_z_statistics (test_bundle_he.BundleHETests.test_extended_he_covers_a6_c2_and_2col_robust_z_statistics)`

This remains a development snapshot, not an accepted production release.

Python compilation, staged whitespace and publication scope checks pass. The previous 145-test receipt remains historical; the full suite was not rerun for this follow-up.
