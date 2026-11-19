"""Enterprise-side crypto helper bridge; keys stay in the parent process."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sme_fraud.method_adapters import _scope
from sme_fraud.method_store import require_fit
from experiments.he_inference.key_manager import load_key,PROVIDER
from experiments.he_inference.protocol import HEUnavailable,canonical,sha
from .blob_store import BlobStore
from .vault import open_private


def linux_path(path):
    path=Path(path).resolve()
    if os.name != 'nt':return str(path)
    if not re.fullmatch('[A-Za-z]:',path.drive):raise ValueError('local Windows drive required')
    return '/mnt/'+path.drive[0].lower()+'/'+path.as_posix()[3:]


class CryptoBridge:
    def __init__(self,enterprise_root,key_file,*,distro=None,python=None):
        distro = distro or os.environ.get('AGENT2_WSL_DISTRO', '').strip() or None
        python = python or os.environ.get('AGENT2_HE_PYTHON', '').strip() or 'python3'
        if distro is not None and not re.fullmatch('[A-Za-z0-9_.-]{1,80}',distro):
            raise ValueError('valid Linux WSL distro name required')
        if any(c in python for c in '\r\n\x00') or not python:
            raise ValueError('valid HE Python executable required')
        self.root=Path(enterprise_root).resolve();self.key_file=Path(key_file).resolve()
        self.distro,self.python=distro,python;self.source=Path(__file__).resolve().parents[2]

    def context(self,scope,bundle):
        tenant,company=_scope(scope);bundle=Path(bundle).resolve();manifest=json.loads((bundle/'manifest.json').read_bytes())
        if manifest['version']!='he4-circuit-build/0.1.0' or manifest['profile'] not in {'rules','graph','statistics','c3'}:raise HEUnavailable('he4_build_incompatible')
        for name in ('server.zip','client.specs.json'):
            if BlobStore.digest(bundle/name)!=manifest['files'][name]:raise HEUnavailable('he4_build_integrity')
        binding=dict(tenant_id=tenant,company_id=company,profile=manifest['profile'],circuit_sha256=manifest['files']['server.zip'],specs_sha256=manifest['files']['client.specs.json'])
        name=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        local=load_key(self.key_file,purpose='state-wrapping',required_provider=PROVIDER)
        key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-he4-private-v1',info=canonical(binding)).derive(local.material)
        return bundle,self.root/name,binding,key

    def _call(self,scope,bundle,action,output=None,**fields):
        import os
        bundle,vault,binding,key=self.context(scope,bundle)
        if action!='provision' and not (vault/'context.sealed').is_file():raise HEUnavailable('he4_key_not_provisioned')
        request=dict(wrapping_key=base64.b64encode(key).decode(),tenant_id=binding['tenant_id'],company_id=binding['company_id'],**fields)
        if os.name!='nt':
            command=[self.python,'-m','experiments.he4.enterprise_helper',action,'--bundle',str(bundle),'--vault',str(vault)]
            if output is not None:command+=['--output',str(output)]
            cwd=self.source
        else:
            from experiments.he_training.runtime import discover_wsl_distro
            distro=self.distro or discover_wsl_distro()
            if not distro:raise HEUnavailable('he4_helper_unavailable')
            command=['wsl.exe','-d',distro,'--cd',linux_path(self.source),'--exec',self.python,'-m','experiments.he4.enterprise_helper',action,'--bundle',linux_path(bundle),'--vault',linux_path(vault)]
            if output is not None:command+=['--output',linux_path(output)]
            cwd=None
        try:
            result=subprocess.run(command,input=canonical(request),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=cwd)
            if result.returncode or len(result.stdout)>16384:raise ValueError('helper failed')
            meta=json.loads(result.stdout)
            if meta['binding']!=binding or not re.fullmatch('key_[a-f0-9]{64}',meta['key_epoch']) or meta['evaluation_keys_sha256']!=BlobStore.digest(vault/'evaluation.keys'):raise ValueError('helper context mismatch')
            return meta
        except (OSError,ValueError,subprocess.SubprocessError,KeyError):raise HEUnavailable('he4_helper_unavailable') from None

    def provision(self,scope,bundle):
        require_fit(scope)
        return self._call(scope,bundle,'provision')

    def encrypt(self,scope,bundle,values,output,*,recover_uncommitted=False):
        bundle,vault,binding,key=self.context(scope,bundle);output=Path(output).resolve()
        manifest_binding=dict(binding,purpose='encrypted-input',operation_id=output.name,input_sha256=sha(canonical(values)))
        if output.exists() and ((output/'manifest.sealed').exists() or not recover_uncommitted):
            try:
                meta=json.loads(open_private(output/'manifest.sealed',key,manifest_binding))
                if meta['binding']!=binding:raise ValueError('context mismatch')
                for index,expected in enumerate(meta['arguments_sha256']):
                    if BlobStore.digest(output/f'argument-{index}.cipher')!=expected:raise ValueError('saved ciphertext changed')
                if meta['evaluation_keys_sha256']!=BlobStore.digest(vault/'evaluation.keys'):raise ValueError('saved public key changed')
                return meta
            except (OSError,ValueError,KeyError):raise HEUnavailable('he4_checkpoint_integrity') from None
        return self._call(scope,bundle,'encrypt',output,values=values,recover_uncommitted=recover_uncommitted)

    def decrypt(self,scope,bundle,cipher,cipher_sha256,output,context):
        bundle,vault,binding,key=self.context(scope,bundle);cipher=Path(cipher).resolve();output=Path(output).resolve()
        if context.get('binding')!=binding:raise HEUnavailable('he4_response_context_mismatch')
        saved=json.loads((vault/'context.json').read_bytes())
        if context['key_epoch']!=saved['key_epoch'] or context['evaluation_keys_sha256']!=saved['evaluation_keys_sha256']:raise HEUnavailable('he4_response_context_mismatch')
        if BlobStore.digest(cipher)!=cipher_sha256:raise HEUnavailable('he4_response_integrity')
        if not output.exists():self._call(scope,bundle,'open',output,ciphertext_file=linux_path(cipher),ciphertext_sha256=cipher_sha256)
        return json.loads(open_private(output,key,dict(binding,purpose='opened-result',ciphertext_sha256=cipher_sha256)))['value']

    def public_key(self,scope,bundle):return self.context(scope,bundle)[1]/'evaluation.keys'

    def public_context(self,scope,bundle):
        """Inspect a provisioned epoch without generating/exporting secret keys."""
        _,vault,binding,_=self.context(scope,bundle)
        if not any((vault/name).exists() for name in ('context.json','context.sealed','evaluation.keys')):
            raise HEUnavailable('he4_key_not_provisioned')
        try:
            meta=json.loads((vault/'context.json').read_bytes())
            if (not (vault/'context.sealed').is_file() or meta['binding']!=binding or
                not re.fullmatch('key_[a-f0-9]{64}',meta['key_epoch']) or
                BlobStore.digest(vault/'evaluation.keys')!=meta['evaluation_keys_sha256']):raise ValueError()
            return meta
        except (OSError,ValueError,KeyError):raise HEUnavailable('he4_key_context_integrity') from None
