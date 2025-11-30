import os
import json
import logging
from typing import Optional, Any, Dict
from urllib.parse import urlparse

from pymemcache.client.base import Client as MCClient
from pymemcache.exceptions import MemcacheError

from config.config import settings

LOG = logging.getLogger("leaflab.cache")

_client: Optional[MCClient] = None


def _make_memcached_client(url: str) -> Optional[MCClient]:

    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 11211
       
        cli = MCClient(
            (host, port),
            connect_timeout=0.8,
            timeout=1.2,
            no_delay=True
        )
    
        try:
            _ = cli.version()
        except Exception:
     
            cli.set(b"__leaflab_ping__", b"1", expire=1)
            cli.get(b"__leaflab_ping__")
        LOG.info("Connected to Memcached at %s:%d", host, port)
        return cli
    except Exception as e:
        LOG.warning("Memcached connect failed: %s; cache disabled (fail-open)", e)
        return None


def _get_client() -> Optional[MCClient]:
 
    global _client
    if _client is not None:
        return _client

    url = settings.CACHE_URL  
    if not url:
        LOG.info("CACHE_URL not set; cache disabled")
        _client = None
        return None

    scheme = urlparse(url).scheme.lower()
    if scheme in ("memcached", "memcache"):
        _client = _make_memcached_client(url)
    else:
        LOG.warning("Unsupported cache scheme '%s' in REDIS_URL. Use memcached://", scheme or "(empty)")
        _client = None
    return _client


def cache_get_bytes(key: str) -> Optional[bytes]:
    cli = _get_client()
    if not cli:
        return None
    try:
   
        k = key.encode("utf-8") if isinstance(key, str) else key
        val = cli.get(k)
      
        return val if isinstance(val, (bytes, bytearray)) else None
    except (MemcacheError, OSError) as e:
        LOG.warning("cache GET failed key=%s: %s (treat as miss)", key, e)
        return None


def cache_set_bytes(key: str, value: bytes, ttl: int) -> None:
    cli = _get_client()
    if not cli:
        return
    try:
        k = key.encode("utf-8") if isinstance(key, str) else key
    
        cli.set(k, value, expire=max(0, int(ttl)))
    except (MemcacheError, OSError) as e:
        LOG.warning("cache SET failed key=%s: %s (ignore)", key, e)


def cache_delete(key: str) -> None:
    cli = _get_client()
    if not cli:
        return
    try:
        k = key.encode("utf-8") if isinstance(key, str) else key
        cli.delete(k)
    except (MemcacheError, OSError):
        pass


def cache_get_json(key: str) -> Optional[Dict[str, Any]]:
    raw = cache_get_bytes(key)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def cache_set_json(key: str, value: Dict[str, Any], ttl: int) -> None:
    try:
        raw = json.dumps(value).encode("utf-8")
    except Exception:
        return
    cache_set_bytes(key, raw, ttl)
