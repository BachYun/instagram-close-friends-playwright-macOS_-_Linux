"""Synthetic tests for the public repository refinements."""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest
from test_helper import m, project, args, fake_browser, fake_page  # reuses fixture setup


@pytest.mark.parametrize('value', [
    'https://example.org:9222', 'http://0.0.0.0:9222', 'http://192.168.1.5:9222',
    'http://127.0.0.1:9222/path', 'http://user:pass@localhost:9222',
    'http://localhost:9222?token=test', 'http://localhost', 'http://localhost:bad',
    'http://127.0.0.1.evil.example:9222',
])
def test_only_loopback_cdp_is_allowed(value):
    with pytest.raises(ValueError):
        m.validate_cdp_url(value)


@pytest.mark.parametrize('value', ['http://127.0.0.1:9222', 'http://localhost:9223/', 'http://[::1]:9222'])
def test_valid_cdp_addresses(value):
    assert m.validate_cdp_url(value) == value.rstrip('/')


def test_username_from_export_paths():
    assert m.username_from_href('https://www.instagram.com/_u/demo_one/') == 'demo_one'
    assert m.username_from_href('https://www.instagram.com/demo_one/') == 'demo_one'
    assert m.username_from_href('https://www.instagram.com@evil.example/demo_one/') is None
    assert m.username_from_href('javascript:alert(1)') is None


def test_headers_after_blank_lines(project):
    m.CSV_PATH.write_text('\n\nUsername\nDEMO_ONE\n@demo_two\n')
    assert m.read_username_csv(m.CSV_PATH) == ['demo_one', 'demo_two']


@pytest.mark.parametrize('bad', [
    'username,result\ndemo_one,confirmed_selected\n',
    'timestamp,username,result\n2026-01-01,demo_one\n',
    'timestamp,username,result\n2026-01-01,demo one,confirmed_selected\n',
    'timestamp,username,result\n2026-01-01,demo_one,confirmed_selected,extra\n',
])
def test_malformed_history_is_not_silently_dropped(project, bad):
    m.PROGRESS_PATH.write_text(bad)
    with pytest.raises(ValueError):
        m.read_progress()


def test_account_binding_rejects_other_account(project):
    m.ensure_account_binding('demo_owner', bind=True)
    before=m.ACCOUNT_PATH.read_bytes()
    assert m.ensure_account_binding(None) == 'demo_owner'
    with pytest.raises(ValueError):
        m.ensure_account_binding('different_owner', bind=True)
    assert m.ACCOUNT_PATH.read_bytes() == before


def test_status_does_not_bind_account_or_change_inputs(project):
    before=m.CSV_PATH.read_bytes()
    assert m.main(['--status','--account','demo_owner']) == 0
    assert not m.ACCOUNT_PATH.exists()
    assert m.CSV_PATH.read_bytes() == before


def test_missing_account_fails_before_browser(project, monkeypatch):
    monkeypatch.setattr(m,'browser_check',Mock(side_effect=AssertionError('browser accessed')))
    with pytest.raises(ValueError,match='--account'):
        m.main(['--limit','1'])


def test_unknown_future_state_cannot_be_clicked(project, monkeypatch):
    m.log_result('new.user', 'future_unrecognized_state')
    p=fake_page();connector=fake_browser(monkeypatch,p)
    assert m.browser_check(['new.user'], args(apply=True)) == 0
    connector.connect_over_cdp.assert_not_called()


def test_preview_failure_preserves_last_meaningful_selection(project, monkeypatch):
    m.log_result('new.user', 'confirmed_selected')
    p=fake_page();fake_browser(monkeypatch,p)
    monkeypatch.setattr(m,'find_row',Mock(side_effect=m.InstagramUnavailable('Something went wrong')))
    assert m.browser_check(['new.user'], args()) == 2
    latest,last=m.latest_results(m.read_progress())
    assert latest['new.user']['result'] == 'confirmed_selected'
    assert last['new.user']['result'] == 'preview_error'


def test_different_account_confirmation_cancels(project, monkeypatch):
    p=fake_page();connector=fake_browser(monkeypatch,p)
    monkeypatch.setattr(m,'terminal_prompt',lambda _: 'ADD 1 TO different_owner')
    assert m.browser_check(['new.user'],args(apply=True)) == 0
    connector.connect_over_cdp.assert_not_called()
    assert not m.PROGRESS_PATH.exists()


def test_pending_queue_can_be_paginated():
    latest={n:{'result':'verification_unresolved'} for n in ['demo_one','demo_two','demo_three']}
    assert m.get_targets(list(latest),args(verify_pending=True,start=2,limit=1),latest)==['demo_two']


@pytest.mark.parametrize('delay', ['nan','inf','-inf','0'])
def test_invalid_pacing_is_rejected(project, delay):
    with pytest.raises(SystemExit):
        m.main(['--status', f'--delay-seconds={delay}'])


def make_archive(project, value, html=False):
    archive=project/'export.zip'
    with zipfile.ZipFile(archive,'w') as zf:
        zf.writestr('connections/followers_and_following/followers_1.'+('html' if html else 'json'),
                    value if html else json.dumps(value))
    return archive


def test_cancel_import_preserves_files(project, monkeypatch):
    archive=make_archive(project,[{'string_list_data':[{'value':'demo_new'}]}])
    before=m.CSV_PATH.read_bytes()
    monkeypatch.setattr(m,'terminal_prompt',lambda _: 'CANCEL')
    with pytest.raises(ValueError,match='cancelled'):
        m.import_export(archive)
    assert m.CSV_PATH.read_bytes()==before
    assert not list(project.glob('followers.before-import*'))


def test_html_import_ignores_outside_links(project, monkeypatch):
    archive=make_archive(project,'<a href="https://www.instagram.com/demo_one/">Name</a>'
                         '<a href="https://evil.example/demo_two/">Wrong</a>',html=True)
    monkeypatch.setattr(m,'terminal_prompt',lambda _: 'IMPORT 1')
    assert m.import_export(archive)==['demo_one']


def test_empty_export_never_erases_snapshot(project):
    archive=make_archive(project,[])
    before=m.CSV_PATH.read_bytes()
    with pytest.raises(ValueError,match='No valid usernames'):
        m.import_export(archive)
    assert m.CSV_PATH.read_bytes()==before


def test_symlink_workspace_file_is_refused(project):
    m.CSV_PATH.unlink()
    target=project/'other'
    target.write_text('demo_one\n')
    m.CSV_PATH.symlink_to(target)
    with pytest.raises(ValueError,match='symlinked'):
        m.configure_paths(project)


def test_raw_error_content_not_logged(project):
    m.log_error('demo_one','search',RuntimeError('private content that must not be written'))
    assert 'private content' not in m.ERROR_PATH.read_text()


def test_intent_is_persisted_before_click(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock();row.inner_text.return_value='new.user\nDemo Name'
    def on_click(**kw):
        assert m.read_progress()[-1]['result']=='selection_attempted_pending_verification'
    row.click.side_effect=on_click
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='NOT_SELECTED'))
    monkeypatch.setattr(m,'observe_selected_after_click',Mock())
    assert m.browser_check(['new.user'],args(apply=True))==0


def test_max_click_cap_counts_attempts_not_save_claims(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock();row.inner_text.return_value='new.user\nDemo'
    finder=Mock(return_value=row)
    monkeypatch.setattr(m,'find_row',finder)
    monkeypatch.setattr(m,'selection_state',Mock(return_value='NOT_SELECTED'))
    monkeypatch.setattr(m,'observe_selected_after_click',Mock())
    assert m.browser_check(['new.user','another.user'],args(apply=True,max_adds=1))==0
    row.click.assert_called_once()
    finder.assert_called_once()


def test_health_error_never_clicks(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    monkeypatch.setattr(m,'current_page_health',Mock(side_effect=m.InstagramUnavailable('Activity restriction.')))
    finder=Mock();monkeypatch.setattr(m,'find_row',finder)
    assert m.browser_check(['new.user'],args(apply=True))==2
    finder.assert_not_called()


def test_selected_on_screen_is_not_clicked_or_declared_verified(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock()
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='SELECTED'))
    assert m.browser_check(['new.user'],args(apply=True))==0
    row.click.assert_not_called()
    assert m.read_progress()[-1]['result']=='selected_pending_verification'
    assert not m.create_reports(['new.user'])['selected']


def test_unknown_icon_is_not_clicked(project,monkeypatch):
    p=fake_page();fake_browser(monkeypatch,p)
    row=Mock()
    monkeypatch.setattr(m,'find_row',Mock(return_value=row))
    monkeypatch.setattr(m,'selection_state',Mock(return_value='UNKNOWN'))
    assert m.browser_check(['new.user'],args(apply=True))==2
    row.click.assert_not_called()


def test_report_text_cannot_become_spreadsheet_formula(project):
    m.write_csv(m.REPORT_PATH,['field'],[['=1+1'],['+cmd'],['normal'],[12]])
    with m.REPORT_PATH.open(newline='') as fh:
        rows=list(csv.reader(fh))
    assert rows==[['field'],["'=1+1"],["'+cmd"],['normal'],['12']]


def test_extra_browser_tabs_refused_before_search(project,monkeypatch):
    p=fake_page();connection=fake_browser(monkeypatch,p)
    connection.connect_over_cdp.return_value.contexts=[SimpleNamespace(pages=[p,p])]
    finder=Mock();monkeypatch.setattr(m,'find_row',finder)
    with pytest.raises(ValueError,match='exactly ONE'):
        m.browser_check(['new.user'],args())
    finder.assert_not_called()


def test_workspace_lock_coordinates_runs(project):
    with m.run_lock():
        with pytest.raises(ValueError):
            with m.run_lock():
                pass


def test_browser_port_lock_coordinates_different_workspaces(tmp_path,monkeypatch):
    monkeypatch.setattr(m.Path,'home',lambda:tmp_path)
    with m.endpoint_lock():
        with pytest.raises(ValueError,match='debugging port'):
            with m.endpoint_lock():
                pass
