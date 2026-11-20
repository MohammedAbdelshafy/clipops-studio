"""Strict origin construction for account-gated Google Cloud Shell preview.

Only the HTTPS hostname published by Cloud Shell is accepted. The Studio
itself continues to bind exclusively to loopback and retains cookie/CSRF gates.
"""
from __future__ import annotations
import re

_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


def cloud_shell_origin(port: int, web_host: str) -> str:
    if type(port) is not int or not 2000 <= port <= 65000:
        raise ValueError('Cloud Shell preview port must be between 2000 and 65000')
    if not isinstance(web_host, str) or not 1 <= len(web_host) <= 220:
        raise ValueError('Cloud Shell WEB_HOST is missing or invalid')
    labels = web_host.split('.')
    if len(labels) < 3 or labels[-2:] != ['cloudshell', 'dev'] or any(not _LABEL.fullmatch(x) for x in labels):
        raise ValueError('WEB_HOST must be the exact *.cloudshell.dev hostname issued by Cloud Shell')
    return f'https://{port}-{web_host}'


def tailnet_origin(value: str) -> str:
    """Allow only an exact private Tailscale Serve DNS origin, never arbitrary URLs.

    Tailscale Funnel (public exposure) is NOT enabled or configured here.
    TLS and tailnet ACLs are supplied by the separately approved Serve device.
    """
    from urllib.parse import urlsplit

    if not isinstance(value, str) or len(value) > 253 or value.strip() != value:
        raise ValueError('Provide a private HTTPS Tailscale Serve address')
    try:
        url = urlsplit(value)
        host = url.hostname
        port = url.port
    except ValueError as exc:
        raise ValueError('Invalid Tailscale HTTPS address') from exc
    if (url.scheme != 'https' or not host or port is not None or
            url.username or url.password or url.path not in ('', '/') or
            url.query or url.fragment or url.netloc != host):
        raise ValueError('Use only https://<device>.<tailnet>.ts.net without a path or port')
    labels = host.split('.')
    if len(labels) < 4 or labels[-2:] != ['ts', 'net'] or not all(_LABEL.fullmatch(label) for label in labels):
        raise ValueError('Only an exact *.ts.net private Tailscale device is allowed')
    return f'https://{host}'
