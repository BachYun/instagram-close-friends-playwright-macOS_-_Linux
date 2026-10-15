"""Publication checks against a temporary local Git repository, without GitHub access."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

SPEC=importlib.util.spec_from_file_location('publish',Path(__file__).resolve().parents[1]/'scripts/check_publish.py')
c=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def test_synthetic_csv_only():
    assert c.inspect_blob('examples/followers.example.csv',c.EXAMPLE)==[]
    assert c.inspect_blob('examples/followers.example.csv',b'personal_name\n')
    assert c.inspect_blob('followers.csv',c.EXAMPLE)


def test_obvious_secret_is_reported_without_printing_value():
    token='ghp_'+'x'*40
    issues=c.inspect_blob('example.py',token.encode())
    assert issues
    assert token not in str(issues)


def test_binary_files_rejected():
    assert c.inspect_blob('README.md',b'bad\0bytes')


def make_git_repo(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'README.md').write_text('# Clean project\n')
    (tmp_path/'PUBLIC_FILES.txt').write_text('README.md\nPUBLIC_FILES.txt\n')
    names=c.public_files(tmp_path)
    c.git(tmp_path,'add','--',*names)
    return names


def test_index_scan_reads_staged_bytes(tmp_path):
    names=make_git_repo(tmp_path)
    assert c.inspect_index(tmp_path,names)==[]
    # A working-tree problem must not silently substitute for the actual staged content.
    (tmp_path/'README.md').write_text('ghp_'+'x'*40)
    assert c.inspect_index(tmp_path,names)==[]
    assert c.inspect_tree(tmp_path,names)
    c.git(tmp_path,'add','README.md')
    assert c.inspect_index(tmp_path,names)


def test_unexpected_staged_private_file_is_refused(tmp_path):
    names=make_git_repo(tmp_path)
    (tmp_path/'followers.csv').write_text('personal_name\n')
    c.git(tmp_path,'add','followers.csv')
    assert any('non-public file' in x for x in c.inspect_index(tmp_path,names))


def test_symlink_is_rejected_before_reading_target(tmp_path):
    names=make_git_repo(tmp_path)
    (tmp_path/'README.md').unlink()
    (tmp_path/'README.md').symlink_to(tmp_path/'does-not-exist')
    c.git(tmp_path,'add','README.md')
    assert any('symlink' in x for x in c.inspect_index(tmp_path,names))
    assert any('symlink' in x for x in c.inspect_tree(tmp_path,names))


def test_manifest_rejects_escape(tmp_path):
    (tmp_path/'PUBLIC_FILES.txt').write_text('../private.txt\n')
    with pytest.raises(ValueError):
        c.public_files(tmp_path)


def test_macos_metadata_not_staged(tmp_path):
    names=make_git_repo(tmp_path)
    (tmp_path/'.DS_Store').write_bytes(b'\0private-system-metadata')
    assert c.inspect_tree(tmp_path,names)==[]
