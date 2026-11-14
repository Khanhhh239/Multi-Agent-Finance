"""Actual Concrete private context recovery through the Windows DPAPI bridge."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from finance_input import AccessScope
from experiments.he4.windows_bridge import CryptoBridge,linux_path
from experiments.he4.blob_store import BlobStore
from experiments.he_inference.key_manager import create_key
from experiments.he_inference.protocol import canonical,sha,HEUnavailable


def run(output,build,public_bundle):
    output=output.resolve()
    if output.exists():raise ValueError('new acceptance directory required')
    output.mkdir(parents=True);start=time.monotonic();key_file=output/'wrapping.dpapi.json';create_key(key_file)
    scope=AccessScope('he4-acceptance',frozenset({'C001'}),'operator',frozenset({'data.import','model.fit'}))
    bridge=CryptoBridge(output/'private',key_file);prepared=bridge.provision(scope,build)
    bundle,vault,binding,_=bridge.context(scope,build);private_before=BlobStore.digest(vault/'context.sealed')
    encrypted=bridge.encrypt(scope,build,[[-123,456]],output/'encrypted')
    # Fresh bridge and fresh helper process read the protected key/context.
    reopened=CryptoBridge(output/'private',key_file)
    if reopened.encrypt(scope,build,[[-123,456]],output/'encrypted')!=encrypted:raise AssertionError('ciphertext replay changed')
    request=output/'cloud-request';request.mkdir()
    (request/'evaluation.keys').hardlink_to(reopened.public_key(scope,build))
    (request/'argument-0.cipher').hardlink_to(output/'encrypted/argument-0.cipher')
    packet=dict(version='he4-native-request/0.1.0',circuit_sha256=binding['circuit_sha256'],evaluation_keys_sha256=encrypted['evaluation_keys_sha256'],arguments_sha256=encrypted['arguments_sha256'])
    (request/'request.json').write_bytes(canonical(packet))
    command=['wsl.exe','-d','Debian','--cd',linux_path(public_bundle),'--exec','/home/sang/.local/share/agent2/he4/bin/python','-m','experiments.he4.public_worker','--bundle',linux_path(build),'--request',linux_path(request),'--circuit-sha256',binding['circuit_sha256']]
    result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise AssertionError('native worker failed')
    cipher=request/'result.cipher';digest=BlobStore.digest(cipher)
    value=reopened.decrypt(scope,build,cipher,digest,output/'opened.sealed',encrypted)
    if value!=579:raise AssertionError('native statistics score mismatch')
    again=CryptoBridge(output/'private',key_file).decrypt(scope,build,cipher,digest,output/'opened.sealed',encrypted)
    if again!=value or BlobStore.digest(vault/'context.sealed')!=private_before:raise AssertionError('private context changed')
    foreign=AccessScope('he4-acceptance',frozenset({'C002'}),'operator',scope.permissions)
    try:reopened.decrypt(foreign,build,cipher,digest,output/'foreign.sealed',encrypted)
    except HEUnavailable:pass
    else:raise AssertionError('foreign context accepted')
    report=dict(actual_concrete=True,dpapi_provider=True,separate_helper_processes=True,private_context_unchanged=True,encrypted_request_reused=True,decrypt_after_restart=True,foreign_context_rejected=True,expected=579,actual=value,seconds=time.monotonic()-start)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--public-bundle',type=Path,required=True);a=p.parse_args();run(a.output,a.build.resolve(),a.public_bundle.resolve())
