"""Removed menus must not leave broken startup, refresh or forecast handlers."""
import pytest
from test_t0_t9_uat_pack import client, core
from test_workspace_usability_fixes import page


@pytest.mark.parametrize('width', [1500, 390])
def test_simplified_navigation_keeps_refresh_and_forecast_validation(client, page, width):
    core(client)
    browser, runtime = page
    browser.set_viewport_size({'width': width, 'height': 1000})
    errors = []
    browser.on('pageerror', lambda err: errors.append(str(err)))
    browser.locator('#refresh').click()
    runtime.expect(browser.locator('#connection-state')).to_contain_text('Đã kết nối')
    for selector in ('.history-menu', '#saved-plans', '#plans-list', '.next-step', '.entry-help',
                     'nav [data-sub="scenarios"]', 'nav .reconciliation-nav'):
        runtime.expect(browser.locator(selector)).to_have_count(0)
    browser.locator('nav [data-view="overview"]').click()
    runtime.expect(browser.locator('#view-overview')).to_be_visible()
    browser.locator('nav [data-view="forecast"]').click()
    browser.locator('#forecast-cutoff').fill('11-11-26')
    browser.locator('#opening-balance').fill('100000000')
    browser.locator('#horizon-weeks').fill('4')
    browser.locator('#forecast-form > details > summary').click()
    browser.locator('#forecast-complete').check()
    browser.locator('#confirmed-weeks').fill('bad')
    browser.locator('#forecast-submit').click()
    runtime.expect(browser.locator('#confirmed-weeks-error')).to_be_visible()
    response = client.post('/v1/predict', json={'cutoff': '2026-11-11', 'opening_balance': 100000000,
        'cash_floor': 0, 'horizon_weeks': 4, 'payments_complete': True, 'simulation_paths': 100, 'shap_limit': 0})
    assert response.status_code == 200, response.text
    browser.route('**/v1/predict', lambda route: route.fulfill(status=200, json=response.json()))
    browser.locator('#confirmed-weeks').fill('1,2')
    browser.locator('#forecast-submit').click()
    runtime.expect(browser.locator('#forecast-output')).to_be_visible()
    assert not errors, errors
    assert not browser.evaluate('document.documentElement.scrollWidth > innerWidth')
