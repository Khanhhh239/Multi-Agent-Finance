"""Dashboard probes are coalesced; launch checks remain uncached."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from portal import server


def test_dashboard_health_coalesces_concurrent_requests():
    with patch.object(server, '_HEALTH_CACHE', {}), patch.object(server, 'health', return_value=True) as probe:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert all(pool.map(server.dashboard_health, ['agent1'] * 16))
        assert probe.call_count == 1


def test_dashboard_health_expires_and_caches_failures():
    with patch.object(server, '_HEALTH_CACHE', {}), patch.object(server.time, 'monotonic') as clock, patch.object(server, 'health', side_effect=[True, False]) as probe:
        clock.return_value = 10.0
        assert server.dashboard_health('agent1') is True
        clock.return_value = 11.0
        assert server.dashboard_health('agent1') is True
        clock.return_value = 12.1
        assert server.dashboard_health('agent1') is False
        assert server.dashboard_health('agent1') is False
        assert probe.call_count == 2
