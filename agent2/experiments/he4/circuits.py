"""Plain-reference functions which Concrete compiles to actual FHE circuits.

No data-dependent Python branches, no model fitting, no decryption on server.
Money arithmetic is exact signed 128-bit represented as little-endian nibbles.
Each source amount is signed int64, with at most four rows in each sum.
"""
import numpy as np

WORD_DIGITS=32
RADIX=16
PRIOR_ROWS=4
CURRENT_ROWS=4
CAP_ROWS=4
STAT_COLUMNS=2
STAT_QUANTUM=1024
GRAPH_NODES=4
GRAPH_FIELDS=4
TOKEN_BYTES=32
TOKEN_DIGITS=64
ARRAY=np.array  # compile process assigns fhe.array; same mathematical program


def add_word(a,b):
    out=[];carry=0
    for i in range(WORD_DIGITS):
        total=a[i]+b[i]+carry
        out.append(total%RADIX);carry=total//RADIX
    return ARRAY(out)


def sum_words(rows):
    value=np.zeros(WORD_DIGITS,dtype=np.int64)
    for i in range(rows.shape[0]):value=add_word(value,rows[i])
    return value


def unsigned_gt(a,b):
    eq=1;gt=0
    for i in range(WORD_DIGITS-1,-1,-1):
        difference=a[i]-b[i]
        gt=(gt+eq*(difference>0))>0
        eq=eq*(difference==0)
    return gt


def signed_gt(a,b):
    sa=a[WORD_DIGITS-1]//8;sb=b[WORD_DIGITS-1]//8
    return ((sa==sb)*unsigned_gt(a,b)+(sa<sb))>0


def subtract_word(a,b):
    one=np.zeros(WORD_DIGITS,dtype=np.int64);one[0]=1
    return add_word(add_word(a,RADIX-1-b),one)


def p1(prior,current,caps,kinds,tolerance,group_mode):
    """Financial P1 arithmetic/predicates; source/time bindings are client-side.

    Every argument is encrypted, including kinds, tolerance and mode. No
    previous-payment predicate or aggregate amount is precomputed in clear.
    """
    zero=np.zeros(WORD_DIGITS,dtype=np.int64)
    prior_total=sum_words(prior);current_total=sum_words(current);cap=sum_words(caps)
    total=add_word(prior_total,current_total);limit=add_word(cap,tolerance)
    previous=0
    for i in range(PRIOR_ROWS):previous=previous+(kinds[i]==1)*signed_gt(prior[i],zero)
    previous=previous>0;positive=signed_gt(current_total,zero);over=signed_gt(total,limit)
    matched=((group_mode==1)*over+(group_mode==0)*previous*positive*over)>0
    excess=subtract_word(total,cap);has_excess=signed_gt(total,cap)
    result=[matched,previous]
    for word in (prior_total,current_total,cap,total):
        for i in range(WORD_DIGITS):result.append(word[i])
    for i in range(WORD_DIGITS):result.append(excess[i]*has_excess)
    return ARRAY(result)


def robust_z(z):
    """Exactly the abs/clip/sum step for the two selected RobustZ columns.

    Client applies the saved median/scale preprocessing and rounds to 1/1024.
    No abs, clip, top-value selection or anomaly score is computed at client.
    Two columns means retained top-5 aggregation is the sum of both columns.
    """
    return np.sum(np.minimum(np.abs(z),10*STAT_QUANTUM))


def graph(tokens,known,active):
    """Equality/link and strong reachability, computed on encrypted tokens.

    Token generation is SHA256(normalized attribute) at enterprise. Every nibble,
    availability bit and active mask is encrypted. Phone/bank are strong links;
    address/tax are context only. Output indices map back to source only at DN.
    """
    links=[]
    for field in range(GRAPH_FIELDS):
        matrix=[]
        for i in range(GRAPH_NODES):
            row=[]
            for j in range(GRAPH_NODES):
                # Subtraction is linear under HE. A zero test then has a
                # five-bit domain, avoiding packed eight-bit comparisons.
                equal=np.sum((tokens[i,field]-tokens[j,field])==0)==TOKEN_DIGITS
                link=equal*known[i,field]*known[j,field]*active[i]*active[j]
                row.append(link if i!=j else 0)
            matrix.append(ARRAY(row))
        links.append(ARRAY(matrix))
    reach=1*((links[0]+links[1])>0)
    diagonal=np.eye(GRAPH_NODES,dtype=np.int64)
    reach=1*((reach+diagonal*active)>0)
    for k in range(GRAPH_NODES):
        via=reach[:,k].reshape((GRAPH_NODES,1))*reach[k,:].reshape((1,GRAPH_NODES))
        # Keep logical matrices integer-valued. NumPy boolean addition is OR,
        # while a one-bit encrypted integer addition can wrap like XOR.
        reach=1*((reach+via)>0)
    result=[]
    for field in range(GRAPH_FIELDS):
        for i in range(GRAPH_NODES):
            for j in range(GRAPH_NODES):result.append(links[field][i,j])
    for i in range(GRAPH_NODES):
        for j in range(GRAPH_NODES):result.append(reach[i,j])
    return ARRAY(result)


def encode_money(value):
    if type(value) is not int or not -(2**63)<=value<2**63:raise ValueError('signed VND must be int64')
    unsigned=value%(1<<128)
    return np.array([(unsigned>>(4*i))&15 for i in range(WORD_DIGITS)],dtype=np.int64)


def decode_money(word):
    values=np.asarray(word,dtype=np.int64)
    if values.shape!=(WORD_DIGITS,) or np.any(values<0) or np.any(values>=RADIX):raise ValueError('invalid money word')
    unsigned=sum(int(v)<<(4*i) for i,v in enumerate(values))
    return unsigned-(1<<128) if unsigned&(1<<127) else unsigned
