"""Enterprise-only input packing. Does not calculate branch decisions/scores."""
import hashlib
import math
import numpy as np
from . import circuits as c


class InputUnavailable(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)


def money_rows(values):
    if len(values)>4:raise InputUnavailable('he_p1_source_limit')
    return np.array([c.encode_money(v) for v in [*values,*([0]*(4-len(values)))]],dtype=np.int64)


def payment(prior,current,invoice_amounts,prior_kinds,*,tolerance=1,group=False):
    """Pack already time/source-validated raw amounts; no totals or hit flags.

    Caller must provide actual allocation rows and invoice base/corrections,
    never a net amount substituted for omitted historical rows.
    """
    if len(prior_kinds)!=len(prior) or any(k not in {'payment','adjustment','reversal'} for k in prior_kinds):raise InputUnavailable('he_p1_kind_missing')
    if type(group) is not bool or type(tolerance) is not int or tolerance<0:raise ValueError('payment profile')
    return (money_rows(prior),money_rows(current),money_rows(invoice_amounts),np.array([int(k=='payment') for k in prior_kinds]+[0]*(4-len(prior)),dtype=np.int64),c.encode_money(tolerance),int(group))


def statistics(values,median,scale):
    """Saved-model preprocessing only. Abs/clip/score run in encrypted circuit."""
    arrays=[np.asarray(v,dtype=float) for v in (values,median,scale)]
    if any(v.shape!=(2,) or not np.isfinite(v).all() for v in arrays) or np.any(arrays[2]<=0):raise InputUnavailable('he_statistics_model_or_features_invalid')
    normalized=(arrays[0]-arrays[1])/arrays[2]
    quantized=np.rint(normalized*c.STAT_QUANTUM)
    if not np.isfinite(quantized).all() or np.any(np.abs(quantized)>16383):raise InputUnavailable('he_statistics_out_of_domain')
    return (quantized.astype(np.int64),)


def graph(entities):
    """Pack normalized attributes, not computed edges or connected components.

    Attributes must already use the retained enterprise normalizers, revision
    resolution and as_of visibility. Missing values keep a zero known mask.
    Identifiers and evidence remain outside the encrypted numeric arrays.
    """
    if not entities:raise InputUnavailable('he_graph_sources_missing')
    if len(entities)>4:raise InputUnavailable('he_graph_node_limit')
    tokens=np.zeros((4,4,c.TOKEN_DIGITS),dtype=np.int64);known=np.zeros((4,4),dtype=np.int64);active=np.zeros(4,dtype=np.int64)
    for i,entity in enumerate(entities):
        if not isinstance(entity,dict) or set(entity)-{'bank_account','phone','address','tax_code'}:raise ValueError('normalized graph fields')
        active[i]=1
        for j,name in enumerate(('bank_account','phone','address','tax_code')):
            value=entity.get(name)
            if value is None or value=='':continue
            if not isinstance(value,str):raise InputUnavailable('he_graph_attribute_invalid')
            digest=hashlib.sha256((name+'\x00'+value).encode()).hexdigest()
            tokens[i,j]=[int(character,16) for character in digest];known[i,j]=1
    if not np.any(known):raise InputUnavailable('he_graph_sources_missing')
    return tokens,known,active


def decode_payment(output):
    value=np.asarray(output)
    if value.shape!=(2+5*c.WORD_DIGITS,) or value[0] not in (0,1) or value[1] not in (0,1):raise ValueError('P1 encrypted output shape')
    return dict(matched=bool(value[0]),previous_payment=bool(value[1]),**{name:c.decode_money(value[2+i*c.WORD_DIGITS:2+(i+1)*c.WORD_DIGITS]) for i,name in enumerate(('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd'))})
