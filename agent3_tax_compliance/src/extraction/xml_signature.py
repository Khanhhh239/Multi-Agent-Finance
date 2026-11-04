"""XML-DSig verification for Vietnamese e-invoices (Decision 1450/QD-TCT layout).

Verifies reference digests and signature values with exclusive canonicalisation.
Not covered: certificate chain to the national root CA and revocation (reported as unchecked).
"""
import base64
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

DS = 'http://www.w3.org/2000/09/xmldsig#'
NS = {'ds': DS}
DIGESTS = {'http://www.w3.org/2000/09/xmldsig#sha1': hashlib.sha1,
           'http://www.w3.org/2001/04/xmlenc#sha256': hashlib.sha256}
SIGNATURE_HASH = {'rsa-sha1': hashes.SHA1, 'rsa-sha256': hashes.SHA256}


def safe_parse(raw: bytes):
    """Parse untrusted XML without entity expansion, DTD loading or network access."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False,
                             huge_tree=False, remove_comments=False)
    root = etree.fromstring(raw, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('DOCTYPE is not allowed in invoice XML')
    return root


def canonical(el) -> bytes:
    return etree.tostring(el, method='c14n', exclusive=True, with_tail=False)


@dataclass
class SignatureResult:
    label: str
    present: bool = False
    digests_ok: bool = False
    value_ok: bool = False
    signer_tax_id: str | None = None
    signing_time: datetime | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.present and self.digests_ok and self.value_ok


def _verify_one(root, sig, label) -> SignatureResult:
    out = SignatureResult(label=label, present=True)
    info = sig.find('ds:SignedInfo', NS)
    alg = info.find('ds:SignatureMethod', NS).get('Algorithm', '')
    suffix = alg.rsplit('#', 1)[-1]
    if suffix not in SIGNATURE_HASH:
        out.notes.append(f'unsupported signature algorithm {suffix}')
        return out
    refs = info.findall('ds:Reference', NS)
    out.digests_ok = bool(refs)
    for ref in refs:
        uri = ref.get('URI', '')
        method = ref.find('ds:DigestMethod', NS).get('Algorithm', '')
        hits = root.xpath('//*[@Id=$i]', i=uri[1:]) if uri.startswith('#') else []
        if method not in DIGESTS or len(hits) != 1:
            out.digests_ok = False
            out.notes.append(f'reference {uri} unresolved or ambiguous')
            continue
        expected = base64.b64decode(ref.find('ds:DigestValue', NS).text or '')
        if DIGESTS[method](canonical(hits[0])).digest() != expected:
            out.digests_ok = False
            out.notes.append(f'digest mismatch for {uri}')
    cert_node = sig.find('.//ds:X509Certificate', NS)
    if cert_node is None or not cert_node.text:
        out.notes.append('no certificate in signature')
        return out
    cert = x509.load_der_x509_certificate(base64.b64decode(cert_node.text))
    try:
        cert.public_key().verify(base64.b64decode(sig.find('ds:SignatureValue', NS).text or ''),
                                 canonical(info), padding.PKCS1v15(), SIGNATURE_HASH[suffix]())
        out.value_ok = True
    except Exception:
        out.notes.append('signature value does not match certificate key')
    m = re.search(r'MST[:=](\d{10}(?:-?\d{3})?)', cert.subject.rfc4514_string())
    out.signer_tax_id = m.group(1) if m else None
    out.not_before = cert.not_valid_before_utc.replace(tzinfo=None)
    out.not_after = cert.not_valid_after_utc.replace(tzinfo=None)
    st = sig.xpath('.//ds:SigningTime', namespaces=NS)
    if st and st[0].text:
        try:
            out.signing_time = datetime.fromisoformat(st[0].text.strip().replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            out.notes.append('unreadable SigningTime')
    return out


def verify_invoice_signatures(root) -> dict[str, SignatureResult]:
    """Return results keyed 'seller' and 'tax_authority'; absent signatures have present=False."""
    results = {}
    for key, path in (('seller', 'DSCKS/NBan/ds:Signature'), ('tax_authority', 'DSCKS/CQT/ds:Signature')):
        sigs = root.xpath(path, namespaces=NS)
        results[key] = _verify_one(root, sigs[0], key) if len(sigs) == 1 else SignatureResult(label=key)
        if len(sigs) > 1:
            results[key].notes.append('multiple signatures; rejected')
    return results
