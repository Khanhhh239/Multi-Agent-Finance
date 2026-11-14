import io,json
from pathlib import Path
import unittest
from unittest.mock import patch
import joblib
import numpy as np
from sme_fraud.ml_estimators import CompanyEstimator,catalog
from sme_fraud.unsupervised_statistics import RobustZ,TailExceedance,ShrunkMahalanobis,MaskedField,Reference
from sme_fraud.score_statistics import empirical_rank
from sme_fraud.features import build_features
from sme_fraud.generate import Generator
from sme_fraud.rules import score_rules
from sme_fraud.feature_contract import digest,current_contract

FROZEN=json.loads((Path(__file__).parent/'fixtures/retained_parity.json').read_text(encoding='utf-8'))


class RetainedCoreTest(unittest.TestCase):
    def test_catalog_and_fit_do_not_accept_supervised_labels(self):
        self.assertEqual({m['id'] for m in catalog()},{'isolation_forest','ecod','lof','autoencoder'})
        self.assertTrue(all(not m['requires_labels'] for m in catalog()))
        for name in ('catboost','bag_injection'):
            with self.assertRaises(ValueError):CompanyEstimator(name)
        with self.assertRaises(TypeError):CompanyEstimator('ecod').fit(FROZEN['train'],np.zeros(120))

    def test_ml_parity_and_scoring_does_not_refit_or_top_k(self):
        x=np.asarray(FROZEN['train']);test=np.asarray(FROZEN['test'])
        for name,expected in FROZEN['estimators'].items():
            with self.subTest(algorithm=name):
                model=CompanyEstimator(name).fit(x)
                stream=io.BytesIO();joblib.dump(model,stream);stream.seek(0);restored=joblib.load(stream)
                with patch.object(restored,'fit',side_effect=AssertionError('Inference refit')):
                    actual=restored.score(test)
                    self.assertEqual(len(actual),5)
                    np.testing.assert_allclose(actual,expected['scores'],rtol=1e-10,atol=1e-10)

    def test_extracted_statistics_are_numerically_unchanged(self):
        x=np.asarray(FROZEN['train']);test=np.asarray(FROZEN['test'])
        for cls in (RobustZ,TailExceedance,ShrunkMahalanobis,MaskedField):
            with self.subTest(method=cls.__name__):
                np.testing.assert_allclose(cls().fit(x).score(test),FROZEN['statistics'][cls.__name__],rtol=1e-10,atol=1e-10)

    def test_reference_rank_ties_and_batch_extremes_preserve_reference(self):
        f=FROZEN['reference'];reference=Reference(f['values']);before=reference.sorted_.copy()
        np.testing.assert_allclose(reference.surprise(f['query']),f['surprise'],rtol=1e-10,atol=1e-10)
        np.testing.assert_array_equal(empirical_rank(f['values'],f['query']),f['rank'])
        reference.surprise([1e20]);np.testing.assert_array_equal(reference.sorted_,before)

    def test_rules_features_and_contract_are_exactly_preserved(self):
        tables=Generator(2000,.005,FROZEN['seed'],2).finalize();features=build_features(tables)
        self.assertEqual(digest(features),FROZEN['engine']['feature_sha256'])
        self.assertEqual(digest(score_rules(tables,features=features)),FROZEN['engine']['rule_sha256'])
        self.assertEqual(current_contract()['fingerprint'],FROZEN['engine']['feature_contract'])


if __name__=='__main__':unittest.main()
