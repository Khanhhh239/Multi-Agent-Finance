from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,OUT
from agent1.synth.einvoice import parse_xml
from agent1.data.schema import quality_gate,inject_errors


def main():
    clean=pd.DataFrame([parse_xml(p) for p in (SYNTH/'tgt/einvoice_xml').glob('*.xml')])
    dirty,truth=inject_errors(clean,rate=.3,seed=1)
    pred=quality_gate(dirty,today='2026-10-16').any_error
    tp=int((truth&pred).sum());n_true=int(truth.sum());n_pred=int(pred.sum())
    row=dict(n=len(clean),precision=tp/max(n_pred,1),recall=tp/max(n_true,1),
             clean_error_rate=float(quality_gate(clean,today='2026-10-16').any_error.mean()),seed=1)
    directory=OUT/'wp0';directory.mkdir(exist_ok=True)
    pd.DataFrame([row]).to_csv(directory/'T0_quality_metrics.csv',index=False)


if __name__=='__main__':main()
