"""Strict origin construction for account-gated Google Cloud Shell preview.

Only the HTTPS hostname published by Cloud Shell is accepted. The Studio
itself continues to bind exclusively to loopback and retains cookie/CSRF gates.
"""
from __future__ import annotations
import re

_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\Z')


def cloud_shell_origin(port: int, web_host: str) -> str:
    if type(port) is not int or not 2000 <= port <= 65000:
        raise ValueError('Cloud Shell preview port must be between 2000 and 65000')
    if not isinstance(web_host, str) or not 1 <= len(web_host) <= 220:
        raise ValueError('Cloud Shell WEB_HOST is missing or invalid')
    labels = web_host.split('.')
    if len(labels) < 3 or labels[-2:] != ['cloudshell', 'dev'] or any(not _LABEL.fullmatch(x) for x in labels):
        raise ValueError('WEB_HOST must be the exact *.cloudshell.dev hostname issued by Cloud Shell')
    return f'https://{port}-{web_host}'
