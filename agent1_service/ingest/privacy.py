import hashlib
import hmac


def anonymize(value, key, namespace='party'):
    if not key or len(key)<32:
        raise ValueError('Khoá HMAC cần ít nhất 32 byte')
    return hmac.new(key,(namespace+'|'+str(value)).encode('utf-8'),hashlib.sha256).hexdigest()
