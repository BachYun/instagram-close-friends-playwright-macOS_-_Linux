"""Local Playwright fixture. ALL browser requests are fulfilled/aborted in-process.
No Instagram network requests or credentials are used.
"""
import os
import importlib.util
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

spec=importlib.util.spec_from_file_location('nvdom', Path(__file__).resolve().parents[1] / 'close_friends_csv.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

HTML='''<!doctype html><html><head><style>
body {font:16px Arial} .row {display:flex;width:450px;height:60px;align-items:center;cursor:pointer;pointer-events:auto}
.content {flex:1} .content div, .content span, .toggle {pointer-events:none}
.icon {width:24px;height:24px;background-color:grey;mask-size:contain}
</style></head><body><h1>Close Friends fixture</h1>
<input placeholder="Search"><input class="wbloks_1" placeholder="Search" dir="auto">
<div class="row" onclick="const el=this.querySelector('.icon'); el.style.maskImage='url(https://fixture.invalid/circle-check__filled__24-4x.png)';">
  <div class="content"><div><div><div><span>demo_account</span></div><span>Display Name</span></div></div></div>
  <div class="toggle" tabindex="0" role="button" aria-label="Toggle checkbox"><div class="icon" style="mask-image:url(https://fixture.invalid/circle__outline__24-4x.png)"></div></div>
</div></body></html>'''

@pytest.mark.browser
@pytest.mark.parametrize('extra_wrappers', [0, 2])
def test_known_dom_shape_and_local_selection(monkeypatch, extra_wrappers):
    if os.getenv('CF_RUN_BROWSER_TESTS') != '1':
        pytest.skip('Set CF_RUN_BROWSER_TESTS=1 to run local Chromium fixture tests')
    executable = os.getenv('CF_TEST_CHROMIUM')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=executable, headless=True)
        context=browser.new_context(service_workers='block')
        intercepted=[]
        def route(request):
            intercepted.append(request.request.url)
            if request.request.resource_type=='document':
                request.fulfill(status=200,content_type='text/html',body=HTML)
            else:
                request.abort()
        context.route('**/*',route)
        page=context.new_page()
        html=HTML.replace('<span>demo_account</span>', '<div>'*extra_wrappers + '<span>demo_account</span>' + '</div>'*extra_wrappers)
        page.set_content(html)
        # Use an in-memory document; URL validation has separate unit coverage.
        monkeypatch.setattr(m, 'is_close_friends_url', lambda value: value == 'about:blank')
        row=m.find_row(page,'demo_account',[])
        assert row is not None
        assert m.selection_state(row)=='NOT_SELECTED'
        assert page.locator('input').nth(0).input_value()==''
        assert page.locator('input').nth(1).input_value()=='demo_account'
        row.click(timeout=5000)
        monkeypatch.setattr(m,'guarded_wait',lambda *a:None)
        m.observe_selected_after_click(page,row,[])
        assert m.selection_state(row)=='SELECTED'
        assert all(x.startswith('https://fixture.invalid/') for x in intercepted)
        # A second visible exact row must be rejected, not guessed.
        page.evaluate("() => {const row=document.querySelector('.row'); row.after(row.cloneNode(true));}")
        assert m.find_row(page,'demo_account',[]) is None
        browser.close()
