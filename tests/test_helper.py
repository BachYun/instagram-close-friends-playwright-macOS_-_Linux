"""Offline tests: temp CSVs and mocked browser calls, never a live Instagram login."""
import ast
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('nv3', Path(__file__).resolve().parents[1] / 'close_friends_csv.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

@pytest.fixture
def project(tmp_path, monkeypatch):
    for attr, name in {
        'CSV_PATH': 'followers.csv', 'PROGRESS_PATH': 'close_friends_progress.csv',
        'REPORT_PATH': 'close_friends_status.csv', 'PENDING_PATH': 'close_friends_pending.csv',
        'SELECTED_PATH': 'close_friends_selected.csv', 'AWAITING_PATH': 'close_friends_awaiting_verification.csv',
        'NEW_PATH': 'close_friends_new_since_export.csv', 'REMOVED_PATH': 'close_friends_no_longer_following.csv',
        'ERROR_PATH': 'close_friends_errors.csv', 'LOCK_PATH': '.close_friends_run.lock',
        'ACCOUNT_PATH': '.close_friends_account.json',
    }.items():
        monkeypatch.setattr(m, attr, tmp_path / name)
    monkeypatch.setattr(m, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(m, 'default_data_dir', lambda: tmp_path)
    m.CSV_PATH.write_text('old.selected\npending.user\nnew.user\n', encoding='utf8')
    return tmp_path


def args(**kw):
    d = dict(apply=False, verify_live=False, verify_pending=False, username=None,
             start=1, limit=5, max_adds=1, no_dark=False, delay_seconds=30, account="demo_owner")
    d.update(kw)
    return SimpleNamespace(**d)


def fake_browser(monkeypatch, page):
    context = SimpleNamespace(pages=[page])
    browser = SimpleNamespace(contexts=[context])
    manager = Mock()
    chromium = SimpleNamespace(connect_over_cdp=Mock(return_value=browser))
    manager.__enter__ = Mock(return_value=SimpleNamespace(chromium=chromium))
    manager.__exit__ = Mock(return_value=False)
    import playwright.sync_api
    monkeypatch.setattr(playwright.sync_api, 'sync_playwright', Mock(return_value=manager))
    monkeypatch.setattr(m, 'current_page_health', Mock())
    monkeypatch.setattr(m, 'guarded_wait', Mock())
    monkeypatch.setattr(m, 'terminal_prompt', Mock(return_value='ADD 1 TO demo_owner'))
    monkeypatch.setattr(m, 'endpoint_lock', contextlib.nullcontext)
    return chromium


def fake_page():
    p = Mock()
    p.url = m.PAGE_URL
    return p


def test_no_automatic_reload_theme_or_navigation():
    tree = ast.parse(Path(m.__file__).read_text())
    forbidden = {'reload','goto','emulate_media','new_context','new_page','dispatch_event'}
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call)]
    assert not [n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    assert not [n for n in calls for k in n.keywords if k.arg == 'force' and isinstance(k.value,ast.Constant) and k.value.value]


def test_csv_deduplicates_header_and_rejects_invalid(project):
    m.CSV_PATH.write_text('\ufeffusername\n@Alice\nalice\nb_ob\n')
    assert m.read_username_csv(m.CSV_PATH) == ['alice','b_ob']
    m.CSV_PATH.write_text('bad name\n')
    with pytest.raises(ValueError): m.read_username_csv(m.CSV_PATH)


def test_latest_pending_not_reported_confirmed(project):
    m.log_result('old.selected','confirmed_selected')
    m.log_result('pending.user','selected_pending_verification')
    result=m.create_reports(m.read_username_csv(m.CSV_PATH))
    assert result['selected']=={'old.selected'}
    assert result['awaiting']=={'pending.user'}
    assert result['pending']=={'pending.user','new.user'}


def test_preview_cannot_change_saved_evidence(project):
    m.log_result('pending.user','selected_pending_verification')
    m.log_result('pending.user','preview_only')
    m.log_result('pending.user','preview_not_found_or_ambiguous')
    latest,last=m.latest_results(m.read_progress())
    assert latest['pending.user']['result']=='selected_pending_verification'
    assert last['pending.user']['result']=='preview_not_found_or_ambiguous'


def test_manual_verification_resolves_pending(project):
    m.log_result('pending.user','stopped_after_click')
    m.log_result('pending.user','verified_selected')
    r=m.create_reports(m.read_username_csv(m.CSV_PATH))
    assert 'pending.user' in r['selected']
    assert 'pending.user' not in r['awaiting']
    m.log_result('pending.user','live_unselected')
    r=m.create_reports(m.read_username_csv(m.CSV_PATH))
    assert 'pending.user' not in r['selected']
    assert 'pending.user' not in r['awaiting']


def test_uncertain_audit_stays_held(project):
    m.log_result('pending.user','stopped_after_click')
    m.log_result('pending.user','verification_unresolved')
    r=m.create_reports(m.read_username_csv(m.CSV_PATH))
    assert 'pending.user' in r['awaiting']
    assert 'pending.user' not in r['selected']


def test_status_does_not_load_browser_or_modify_log(project, monkeypatch):
    m.log_result('old.selected','confirmed_selected')
    before=m.PROGRESS_PATH.read_bytes()
    monkeypatch.setattr(m,'browser_check',Mock(side_effect=AssertionError('browser used')))
    assert m.main(['--status'])==0
    assert m.PROGRESS_PATH.read_bytes()==before
    assert m.SELECTED_PATH.is_file()
    assert m.AWAITING_PATH.is_file()


def test_unknown_username_fails_before_browser(project):
    with pytest.raises(ValueError):
        m.get_targets(['new.user'], args(username='someone_else'), {})


def test_pending_queue_selects_only_uncertain(project):
    latest={'old.selected':{'result':'confirmed_selected'},
            'pending.user':{'result':'stopped_after_click'}}
    assert m.get_targets(['old.selected','pending.user','new.user'],args(verify_pending=True),latest)==['pending.user']


def test_account_url_validation():
    assert m.is_close_friends_url(m.PAGE_URL)
    assert not m.is_close_friends_url('https://www.instagram.com.evil.example/accounts/close_friends/')
    assert not m.is_close_friends_url('https://www.instagram.com/accounts/close_friends_malicious')
    assert not m.is_close_friends_url('http://www.instagram.com/accounts/close_friends/')


@pytest.mark.parametrize('status,method,resource,expected',[
    (429,'GET','fetch',True),(403,'GET','document',True),(400,'POST','xhr',True),
    (503,'GET','document',True),(200,'POST','xhr',False),(405,'GET','fetch',False),
])
def test_error_watcher(status,method,resource,expected):
    rejected=[]
    watcher=m.make_response_watcher(rejected)
    watcher(SimpleNamespace(url='https://www.instagram.com/test?private=hidden',status=status,
        request=SimpleNamespace(method=method,resource_type=resource)))
    assert bool(rejected)==expected
    assert 'hidden' not in str(rejected)
    watcher(SimpleNamespace(url='https://instagram.com.evil.example/test',status=429,
        request=SimpleNamespace(method='POST',resource_type='fetch')))
    assert len(rejected)==int(expected)


@pytest.mark.parametrize('text',["Something went wrong",'Too many requests','Please wait a few minutes'])
def test_error_ui_stops_without_action(text):
    p=fake_page();p.is_closed.return_value=False
    p.locator.return_value.inner_text.return_value=text
    with pytest.raises(m.InstagramUnavailable):m.current_page_health(p,[])
    p.reload.assert_not_called();p.goto.assert_not_called()


def test_manual_gate_demands_new_document(monkeypatch):
    p=fake_page();p.evaluate.side_effect=[1000,1000]
    monkeypatch.setattr(m,'terminal_prompt',lambda _: 'REFRESHED demo_owner')
    monkeypatch.setattr(m,'current_page_health',lambda *a:None)
    with pytest.raises(m.InstagramUnavailable,match='No full refresh'):
        m.confirm_manual_refresh(p,[],"demo_owner")
    p.reload.assert_not_called()


def test_manual_gate_accepts_changed_document(monkeypatch):
    p=fake_page();p.evaluate.side_effect=[1000,2000]
    monkeypatch.setattr(m,'terminal_prompt',lambda _: 'REFRESHED demo_owner')
    monkeypatch.setattr(m,'current_page_health',lambda *a:None)
    m.confirm_manual_refresh(p,[],"demo_owner")
    p.reload.assert_not_called()


def test_eof_has_actionable_error(monkeypatch):
    monkeypatch.setattr('builtins.input',Mock(side_effect=EOFError()))
    with pytest.raises(ValueError,match='saved .py file'):m.terminal_prompt('test')


def test_apply_clicks_once_and_keeps_pending(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock();row.inner_text.return_value='new.user\nNew User'
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='NOT_SELECTED'))
    monkeypatch.setattr(m,'observe_selected_after_click',Mock())
    assert m.browser_check(['new.user'],args(apply=True))==0
    row.click.assert_called_once_with(timeout=5000)
    assert [x['result'] for x in m.read_progress()]==['selection_attempted_pending_verification','selected_pending_verification']
    p.reload.assert_not_called();p.emulate_media.assert_not_called()
    assert m.create_reports(['new.user'])['selected']==set()


def test_apply_skips_previous_pending(project,monkeypatch):
    m.log_result('pending.user','stopped_after_click')
    p=fake_page();connector=fake_browser(monkeypatch,p)
    assert m.browser_check(['pending.user'],args(apply=True))==0
    connector.connect_over_cdp.assert_not_called()


def test_failure_after_click_never_confirmed_or_retried(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock();row.inner_text.return_value='new.user\nNew User'
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='NOT_SELECTED'))
    monkeypatch.setattr(m,'observe_selected_after_click',Mock(side_effect=m.InstagramUnavailable('Something went wrong')))
    assert m.browser_check(['new.user'],args(apply=True))==2
    row.click.assert_called_once()
    assert m.read_progress()[-1]['result']=='stopped_after_click'
    assert not m.create_reports(['new.user'])['selected']


def test_interruption_keeps_intent(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock();row.inner_text.return_value='new.user\nNew User'
    row.click.side_effect=KeyboardInterrupt()
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='NOT_SELECTED'))
    assert m.browser_check(['new.user'],args(apply=True))==2
    assert m.read_progress()[-1]['result']=='stopped_after_click'
    assert m.ERROR_PATH.is_file()


def test_verification_does_not_click(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock()
    monkeypatch.setattr(m,'confirm_manual_refresh',Mock())
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='SELECTED'))
    assert m.browser_check(['new.user'],args(verify_live=True))==0
    row.click.assert_not_called()
    assert m.read_progress()[-1]['result']=='verified_selected'
    m.confirm_manual_refresh.assert_called_once()


def test_import_preserves_progress(project, monkeypatch):
    monkeypatch.setattr(m, "terminal_prompt", lambda _: "IMPORT 2")
    m.log_result('old.selected','confirmed_selected')
    before=m.PROGRESS_PATH.read_bytes()
    archive=project/'new.zip'
    with zipfile.ZipFile(archive,'w') as zf:
        zf.writestr('connections/followers_and_following/followers_1.json',json.dumps([
            {'string_list_data':[{'value':'old.selected'}]},
            {'string_list_data':[{'value':'another.new'}]},
        ]))
        zf.writestr('connections/followers_and_following/following.json',json.dumps([
            {'string_list_data':[{'value':'must.not.include'}]}]))
    assert m.import_export(archive)==['old.selected','another.new']
    assert m.PROGRESS_PATH.read_bytes()==before
    assert m.NEW_PATH.read_text().strip().splitlines()[-1]=='another.new'
    assert list(project.glob('followers.before-import-*.csv'))






def test_duplicate_lock_is_refused(project):
    with m.run_lock():
        with pytest.raises(ValueError,match='Another run'):
            with m.run_lock():pass
    with m.run_lock():pass
