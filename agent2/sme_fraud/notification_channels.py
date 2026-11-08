"""Explicit SMTP and Zalo OA GMF transports. Dry-run never enters these adapters."""
from email.message import EmailMessage
from email.utils import format_datetime
import json
import os
import smtplib
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


class DeliveryError(Exception):
    def __init__(self, code, *, retryable=False, uncertain=False, retry_after=60):
        super().__init__(code)
        self.code, self.retryable, self.uncertain = code, retryable, uncertain
        self.retry_after = max(5, min(86400, retry_after))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def smtp_send(job, config, now):
    settings = config.get('smtp', {})
    message = EmailMessage()
    message['Subject'] = job['subject']
    message['From'] = settings['from_address']
    message['To'] = job['recipient']
    message['Message-ID'] = '<'+job['job_id']+'@sosoat.local>'
    message['Date'] = format_datetime(now)
    message.set_content(job['body'])
    context = ssl.create_default_context()
    client = None
    sending = False
    try:
        if settings.get('tls', 'starttls') == 'ssl':
            client = smtplib.SMTP_SSL(settings['host'], settings.get('port', 465), timeout=15, context=context)
        else:
            client = smtplib.SMTP(settings['host'], settings.get('port', 587), timeout=15)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        if settings.get('username'):
            password = os.environ.get(settings.get('password_env', 'SME_SMTP_PASSWORD'))
            if not password:
                raise DeliveryError('smtp_credentials_missing')
            client.login(settings['username'], password)
        sending = True
        refused = client.send_message(message)
        if refused:
            raise DeliveryError('smtp_recipient_refused')
        return str(message['Message-ID'])
    except DeliveryError:
        raise
    except smtplib.SMTPResponseException as error:
        raise DeliveryError('smtp_'+str(error.smtp_code), retryable=400 <= error.smtp_code < 500) from None
    except smtplib.SMTPRecipientsRefused:
        raise DeliveryError('smtp_recipient_refused') from None
    except (OSError, smtplib.SMTPException):
        raise DeliveryError('smtp_connection_failed', retryable=not sending, uncertain=sending) from None
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass


def zalo_request(job, token):
    # GMF text messages to an explicitly configured internal OA group.
    payload = dict(recipient=dict(group_id=job['recipient']), message=dict(text=job['subject']+'\n'+job['body']))
    return Request('https://openapi.zalo.me/v3.0/oa/group/message',
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json', 'access_token':token}, method='POST')


def zalo_send(job, config, now):
    token = os.environ.get(config.get('zalo', {}).get('access_token_env', 'SME_ZALO_OA_TOKEN'))
    if not token:
        raise DeliveryError('zalo_credentials_missing')
    try:
        # Never forward the OA credential to a redirect destination.
        with build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context())).open(zalo_request(job, token), timeout=15) as response:
            result = json.loads(response.read(65536))
    except HTTPError as error:
        retry = error.code == 429 or 500 <= error.code < 600
        value = error.headers.get('Retry-After', '60')
        raise DeliveryError('zalo_http_'+str(error.code), retryable=retry,
                            retry_after=int(value) if value.isdigit() else 60) from None
    except (TimeoutError, URLError, OSError, ValueError):
        # The request may have reached the provider. Human reconciliation is
        # safer than silently producing a second financial alert.
        raise DeliveryError('zalo_response_unknown', uncertain=True) from None
    if result.get('error') != 0:
        raise DeliveryError('zalo_api_'+str(result.get('error', 'invalid_response')))
    provider_id = result.get('data', {}).get('message_id')
    if not isinstance(provider_id, str) or not provider_id:
        raise DeliveryError('zalo_message_id_missing', uncertain=True)
    return provider_id


TRANSPORTS = {'email': smtp_send, 'zalo': zalo_send}
