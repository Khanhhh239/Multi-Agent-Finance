"""XML-DSig verification for Vietnamese e-invoices (Decision 1450/QD-TCT layout).

Verifies reference digests and signature values with Inclusive C14N and Exclusive C14N
plus enveloped-signature transforms, blocks XML Signature Wrapping (XSW) by requiring
unique HDon/DLHDon coverage, detects self-signed certificates (and verifies against
configured CA roots when present), and validates tax-authority Subject DN on CQT signatures.
"""
import base64
import copy
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

DS = 'http://www.w3.org/2000/09/xmldsig#'
EC = 'http://www.w3.org/2001/10/xml-exc-c14n#'
NS = {'ds': DS, 'ec': EC}
ENVELOPED_TRANSFORM = 'http://www.w3.org/2000/09/xmldsig#enveloped-signature'

# Map Canonicalization / Transform Algorithm URIs -> (exclusive: bool, with_comments: bool)
C14N_ALGORITHMS = {
    'http://www.w3.org/TR/2001/REC-xml-c14n-20010315': (False, False),
    'http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments': (False, True),
    'http://www.w3.org/2006/12/xml-c14n11': (False, False),
    'http://www.w3.org/2006/12/xml-c14n11#WithComments': (False, True),
    'http://www.w3.org/2001/10/xml-exc-c14n#': (True, False),
    'http://www.w3.org/2001/10/xml-exc-c14n#WithComments': (True, True),
}

DIGESTS = {
    'http://www.w3.org/2000/09/xmldsig#sha1': hashlib.sha1,
    'http://www.w3.org/2001/04/xmlenc#sha256': hashlib.sha256,
    'http://www.w3.org/2001/04/xmldsig-more#sha384': hashlib.sha384,
    'http://www.w3.org/2001/04/xmlenc#sha512': hashlib.sha512,
}
SIGNATURE_HASH = {
    'rsa-sha1': hashes.SHA1,
    'rsa-sha256': hashes.SHA256,
    'rsa-sha384': hashes.SHA384,
    'rsa-sha512': hashes.SHA512,
}

DEFAULT_CA_ROOTS_DIR = Path(__file__).resolve().parents[2] / 'configs' / 'ca_roots'

TAX_AUTHORITY_MARKERS = (
    'tong cuc thue',
    'cuc thue',
    'co quan thue',
    'bo tai chinh',
    'general department of taxation',
)


def _fold_ascii(text: str) -> str:
    t = unicodedata.normalize('NFD', (text or '').replace('đ', 'd').replace('Đ', 'D'))
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', t.casefold()).split())


def safe_parse(raw: bytes):
    """Parse untrusted XML without entity expansion, DTD loading or network access."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False,
                             huge_tree=False, remove_comments=False)
    root = etree.fromstring(raw, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('DOCTYPE is not allowed in invoice XML')
    return root


def canonical(el, *, exclusive: bool = True, with_comments: bool = False,
              inclusive_ns_prefixes: list[str] | None = None) -> bytes:
    kwargs = dict(method='c14n', exclusive=exclusive, with_comments=with_comments, with_tail=False)
    if exclusive and inclusive_ns_prefixes:
        kwargs['inclusive_ns_prefixes'] = inclusive_ns_prefixes
    return etree.tostring(el, **kwargs)


def _inclusive_prefixes(method_or_transform_el) -> list[str] | None:
    if method_or_transform_el is None:
        return None
    inc = method_or_transform_el.find('ec:InclusiveNamespaces', NS)
    if inc is not None and inc.get('PrefixList'):
        return [p for p in inc.get('PrefixList', '').split() if p]
    return None


def _index_path(root, el) -> tuple[int, ...]:
    idx = []
    cur = el
    while cur is not root:
        parent = cur.getparent()
        if parent is None:
            raise ValueError('element is not inside root')
        idx.append(parent.index(cur))
        cur = parent
    return tuple(reversed(idx))


def _follow_index_path(root, path: tuple[int, ...]):
    cur = root
    for i in path:
        cur = cur[i]
    return cur


def _canonicalize_reference_target(root, sig, target, transforms_el) -> tuple[bytes | None, str | None]:
    """Apply XML-DSig Reference transforms (enveloped-signature, Inclusive/Exclusive C14N)."""
    # Per W3C XML-DSig §4.3.3.2, when no C14N transform is specified, Inclusive C14N 1.0 without comments applies.
    exclusive, with_comments = False, False
    enveloped = False
    inc_prefixes = None
    if transforms_el is not None:
        for tr in transforms_el.findall('ds:Transform', NS):
            alg = (tr.get('Algorithm') or '').strip()
            if alg == ENVELOPED_TRANSFORM:
                enveloped = True
            elif alg in C14N_ALGORITHMS:
                exclusive, with_comments = C14N_ALGORITHMS[alg]
                inc_prefixes = _inclusive_prefixes(tr)
            else:
                return None, f'unsupported transform {alg}'
    node = target
    if enveloped:
        try:
            target_idx = _index_path(root, target)
            sig_idx = _index_path(root, sig)
            root_copy = copy.deepcopy(root)
            node = _follow_index_path(root_copy, target_idx)
            sig_copy = _follow_index_path(root_copy, sig_idx)
            if sig_copy.getparent() is not None:
                sig_copy.getparent().remove(sig_copy)
        except Exception:
            return None, 'enveloped transform target lost'
    return canonical(node, exclusive=exclusive, with_comments=with_comments, inclusive_ns_prefixes=inc_prefixes), None


def _is_self_signed(cert: x509.Certificate) -> bool:
    """True when Subject == Issuer or the certificate signature verifies under its own public key."""
    if cert.issuer == cert.subject:
        return True
    try:
        pub = cert.public_key()
        if cert.signature_hash_algorithm is not None:
            pub.verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
            return True
    except Exception:
        pass
    return False


def load_ca_roots(ca_roots_dir: Path | None = None) -> list[x509.Certificate]:
    folder = Path(ca_roots_dir) if ca_roots_dir is not None else DEFAULT_CA_ROOTS_DIR
    if not folder.exists() or not folder.is_dir():
        return []
    certs = []
    for path in sorted(folder.glob('*.pem')) + sorted(folder.glob('*.crt')) + sorted(folder.glob('*.cer')):
        raw = path.read_bytes()
        try:
            if b'-----BEGIN CERTIFICATE-----' in raw:
                certs.extend(x509.load_pem_x509_certificates(raw))
            else:
                certs.append(x509.load_der_x509_certificate(raw))
        except Exception:
            continue
    return certs


def verify_cert_against_roots(cert: x509.Certificate, roots: list[x509.Certificate]) -> bool | None:
    """None when no CA roots are configured; True if signed by a configured trusted CA; False otherwise."""
    if not roots:
        return None
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    for ca in roots:
        if ca.public_bytes(serialization.Encoding.DER) == cert_der:
            return True
        if cert.issuer != ca.subject:
            continue
        try:
            if cert.signature_hash_algorithm is not None:
                ca.public_key().verify(cert.signature, cert.tbs_certificate_bytes,
                                       padding.PKCS1v15(), cert.signature_hash_algorithm)
                return True
        except Exception:
            continue
    return False


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
    signed_element_ids: tuple[str, ...] = ()
    self_signed: bool = False
    chain_trusted: bool | None = None
    subject_dn: str = ''
    issuer_dn: str = ''
    cert_sha256: str = ''

    @property
    def verified(self) -> bool:
        return self.present and self.digests_ok and self.value_ok


def is_tax_authority_cert(cqt_sig: SignatureResult, seller_sig: SignatureResult | None = None,
                          seller_tax_id: str | None = None) -> tuple[bool, str]:
    """Verify CQT certificate Subject DN belongs to GDT / Tax Authority and is distinct from seller."""
    if not cqt_sig.present or not cqt_sig.subject_dn:
        return False, 'authority certificate missing'
    if seller_sig and seller_sig.cert_sha256 and cqt_sig.cert_sha256 == seller_sig.cert_sha256:
        return False, 'authority signature reuses seller certificate'
    seller_clean = (seller_tax_id or '').replace('-', '').strip()
    cqt_mst = (cqt_sig.signer_tax_id or '').replace('-', '').strip()
    if seller_clean and cqt_mst and (cqt_mst == seller_clean or (len(seller_clean) in (10, 13) and cqt_mst[:10] == seller_clean[:10])):
        return False, 'authority certificate carries seller tax id'
    folded = _fold_ascii(cqt_sig.subject_dn)
    has_authority_dn = any(m in folded for m in TAX_AUTHORITY_MARKERS) or bool(re.search(r'\b(?:tct|gdt)\b', folded))
    if not has_authority_dn:
        return False, f'authority certificate Subject DN not recognised as tax authority: {cqt_sig.subject_dn[:120]}'
    return True, ''


def _verify_one(root, sig, label: str, ca_roots: list[x509.Certificate] | None = None) -> SignatureResult:
    out = SignatureResult(label=label, present=True)
    info = sig.find('ds:SignedInfo', NS)
    if info is None:
        out.notes.append('missing SignedInfo')
        return out
    sig_method_el = info.find('ds:SignatureMethod', NS)
    alg = sig_method_el.get('Algorithm', '') if sig_method_el is not None else ''
    suffix = alg.rsplit('#', 1)[-1]
    if suffix not in SIGNATURE_HASH:
        out.notes.append(f'unsupported signature algorithm {suffix}')
        return out

    c14n_el = info.find('ds:CanonicalizationMethod', NS)
    c14n_alg = (c14n_el.get('Algorithm') or 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315').strip() if c14n_el is not None else 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
    if c14n_alg not in C14N_ALGORITHMS:
        out.notes.append(f'unsupported canonicalization algorithm {c14n_alg}')
        return out
    info_excl, info_comments = C14N_ALGORITHMS[c14n_alg]
    info_prefixes = _inclusive_prefixes(c14n_el)

    dlhdon_direct = root.findall('DLHDon')
    all_dlhdon = root.xpath('//*[local-name()="DLHDon"]')
    dlhdon_node = dlhdon_direct[0] if len(dlhdon_direct) == 1 else None
    mccqt_node = root.find('MCCQT')
    unique_dlhdon = (dlhdon_node is not None and len(dlhdon_direct) == 1
                     and len(all_dlhdon) == 1 and all_dlhdon[0] is dlhdon_node)

    refs = info.findall('ds:Reference', NS)
    out.digests_ok = bool(refs)
    covers_dlhdon = False
    covers_mccqt = False
    signed_ids: list[str] = []

    for ref in refs:
        uri = ref.get('URI', '')
        dm_el = ref.find('ds:DigestMethod', NS)
        method = dm_el.get('Algorithm', '') if dm_el is not None else ''
        transforms_el = ref.find('ds:Transforms', NS)
        target = None
        if uri == '':
            # Whole-document reference requires enveloped-signature transform so signature does not hash itself.
            has_enveloped = transforms_el is not None and any(
                (t.get('Algorithm') or '').strip() == ENVELOPED_TRANSFORM for t in transforms_el.findall('ds:Transform', NS)
            )
            if has_enveloped:
                target = root
                signed_ids.append('#document')
        elif uri.startswith('#') and len(uri) > 1:
            ref_id = uri[1:]
            all_id_hits = root.xpath('//*[@Id=$i or @id=$i or @ID=$i]', i=ref_id)
            exact_hits = root.xpath('//*[@Id=$i]', i=ref_id) or all_id_hits
            if len(all_id_hits) == 1 and len(exact_hits) == 1:
                target = exact_hits[0]
                signed_ids.append(ref_id)
        if method not in DIGESTS or target is None:
            out.digests_ok = False
            out.notes.append(f'reference {uri} unresolved or ambiguous')
            continue
        c14n_bytes, tr_err = _canonicalize_reference_target(root, sig, target, transforms_el)
        if tr_err or c14n_bytes is None:
            out.digests_ok = False
            out.notes.append(tr_err or f'canonicalization failed for {uri}')
            continue
        dv_el = ref.find('ds:DigestValue', NS)
        try:
            expected = base64.b64decode((dv_el.text if dv_el is not None else '') or '')
        except Exception:
            expected = b''
        if DIGESTS[method](c14n_bytes).digest() != expected:
            out.digests_ok = False
            out.notes.append(f'digest mismatch for {uri}')
            continue
        if unique_dlhdon and (target is dlhdon_node or target is root):
            covers_dlhdon = True
        if mccqt_node is not None and (target is mccqt_node or target is root):
            covers_mccqt = True

    out.signed_element_ids = tuple(signed_ids)
    if not unique_dlhdon:
        out.digests_ok = False
        out.notes.append('multiple or wrapped DLHDon elements detected (XSW)')
    elif label == 'seller' and out.digests_ok and not covers_dlhdon:
        out.digests_ok = False
        out.notes.append('signed reference does not cover HDon/DLHDon')
    elif label == 'tax_authority' and out.digests_ok and not (covers_dlhdon or covers_mccqt):
        out.digests_ok = False
        out.notes.append('authority signature reference does not cover HDon/DLHDon or MCCQT')

    cert_node = sig.find('.//ds:X509Certificate', NS)
    if cert_node is None or not cert_node.text:
        out.notes.append('no certificate in signature')
        return out
    cert_der = base64.b64decode(cert_node.text)
    cert = x509.load_der_x509_certificate(cert_der)
    out.cert_sha256 = hashlib.sha256(cert_der).hexdigest()
    out.subject_dn = cert.subject.rfc4514_string()
    out.issuer_dn = cert.issuer.rfc4514_string()
    out.self_signed = _is_self_signed(cert)
    if ca_roots is not None:
        out.chain_trusted = verify_cert_against_roots(cert, ca_roots)

    try:
        sv_el = sig.find('ds:SignatureValue', NS)
        sig_bytes = base64.b64decode((sv_el.text if sv_el is not None else '') or '')
        info_bytes = canonical(info, exclusive=info_excl, with_comments=info_comments, inclusive_ns_prefixes=info_prefixes)
        cert.public_key().verify(sig_bytes, info_bytes, padding.PKCS1v15(), SIGNATURE_HASH[suffix]())
        out.value_ok = True
    except Exception:
        out.notes.append('signature value does not match certificate key')

    # Support 10-digit enterprise MST, 13-digit branch MST (10-3 or 13), and 12-digit CCCD personal tax ID (TT 86/2024)
    subj_texts = ' ; '.join([out.subject_dn] + [str(a.value) for a in cert.subject])
    m = re.search(r'(?:MST|UID)[:=](\d{10}-\d{3}|\d{13}|\d{12}|\d{10})(?!\d)', subj_texts)
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


def verify_invoice_signatures(root, *, ca_roots_dir: Path | None = None) -> dict[str, SignatureResult]:
    """Return results keyed 'seller' and 'tax_authority'; absent signatures have present=False."""
    roots = load_ca_roots(ca_roots_dir)
    results = {}
    for key, path in (('seller', 'DSCKS/NBan/ds:Signature'), ('tax_authority', 'DSCKS/CQT/ds:Signature')):
        sigs = root.xpath(path, namespaces=NS)
        results[key] = _verify_one(root, sigs[0], key, roots) if len(sigs) == 1 else SignatureResult(label=key)
        if len(sigs) > 1:
            results[key].notes.append('multiple signatures; rejected')
    return results
