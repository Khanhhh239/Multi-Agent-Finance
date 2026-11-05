"""Polite HTTP fetching: robots.txt check before every request, minimum interval, identified user agent, disk cache."""
import gzip
import hashlib
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse


class FetchError(RuntimeError):
    pass


class PoliteFetcher:
    def __init__(self, user_agent: str, min_interval: float, cache_dir: Path, opener=None):
        self.ua, self.min_interval, self.cache = user_agent, float(min_interval), Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._robots, self._last = {}, 0.0
        self._open = opener or self._urlopen
        self.requests = 0

    def _urlopen(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': self.ua, 'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
            if r.headers.get('Content-Encoding') == 'gzip':
                data = gzip.decompress(data)
            return data

    def allowed(self, url: str) -> bool:
        host = urlparse(url)
        root = f'{host.scheme}://{host.netloc}'
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(self._get(root + '/robots.txt', check_robots=False).decode('utf-8', 'replace').splitlines())
            self._robots[root] = rp
        return self._robots[root].can_fetch(self.ua, url)

    def _get(self, url, check_robots=True):
        if check_robots and not self.allowed(url):
            raise FetchError(f'robots.txt disallows {url}')
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        last_error = None
        for attempt in range(3):
            try:
                self._last = time.monotonic()
                self.requests += 1
                return self._open(url)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                time.sleep(self.min_interval * (attempt + 2))
        raise FetchError(f'{url}: {last_error}')

    def get(self, url: str, cache_key: str | None = None, refresh: bool = False) -> bytes:
        """Fetch with a gzip disk cache keyed by cache_key (for example url plus sitemap lastmod)."""
        key = hashlib.sha256((cache_key or url).encode()).hexdigest()
        path = self.cache / key[:2] / f'{key}.gz'
        if path.exists() and not refresh:
            return gzip.decompress(path.read_bytes())
        data = self._get(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(data))
        return data
