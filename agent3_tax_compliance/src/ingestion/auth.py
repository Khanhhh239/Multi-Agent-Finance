import hashlib
import hmac

from ..domain.taxpayer import AccessContext
from .models import IngestionError


def authenticate(settings,authorization):
    if not authorization or not authorization.startswith('Bearer ') or len(authorization)>4096:
        raise IngestionError('ACCESS_DENIED','A configured Bearer credential is required.',status=401,
                             next_action='Authenticate with a credential granted for this tenant/taxpayer.')
    value=hashlib.sha256(authorization[7:].encode()).hexdigest()
    for grant in settings.auth_grants:
        if hmac.compare_digest(value,grant.token_sha256):
            return AccessContext(actor_id=grant.actor_id,tenant_id=grant.tenant_id,
                                 taxpayer_ids=grant.taxpayer_ids,permissions=grant.permissions)
    raise IngestionError('ACCESS_DENIED','Invalid credential.',status=401,next_action='Use a configured credential.')
