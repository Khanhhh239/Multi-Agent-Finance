import numpy as np
import pandas as pd
from agent1.eval.domain_distance import split_companies,auc_cluster_ci


def test_domain_partition_does_not_share_company_and_is_reproducible():
    frame=pd.DataFrame({'firm_id':np.repeat(list('abcdef'),5),'x':np.arange(30)})
    train,test=split_companies(frame)
    assert not set(train.firm_id)&set(test.firm_id)
    assert len(train)+len(test)==len(frame)
    pd.testing.assert_frame_equal(test,split_companies(frame)[1])


def test_domain_auc_bootstrap_keeps_both_domains_and_company_clusters():
    y=np.repeat([0,1],20);p=np.where(y==1,.9,.1);firm=np.tile(np.repeat(['a','b'],10),2)
    assert auc_cluster_ci(y,p,y,firm,n_boot=20)==(1.,1.)
