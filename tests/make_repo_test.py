from __future__ import unicode_literals

import io
import mock
import os.path
import pytest
import re
import subprocess

from pre_commit_mirror_maker.make_repo import _apply_version_and_commit
from pre_commit_mirror_maker.make_repo import _ruby_get_package_version_output
from pre_commit_mirror_maker.make_repo import cwd
from pre_commit_mirror_maker.make_repo import format_files_to_directory
from pre_commit_mirror_maker.make_repo import get_output
from pre_commit_mirror_maker.make_repo import make_repo
from pre_commit_mirror_maker.make_repo import ruby_get_package_versions


def test_get_output():
    output = get_output('echo', 'hi')
    assert output == 'hi\n'


@pytest.mark.integration
def test_ruby_get_package_version_output():
    ret = _ruby_get_package_version_output('scss-lint')
    # We expect the output to look something like this:
    # 'scss-lint (1.2.3, 1.1.0, ...)\n'
    ret_re = re.compile(r'^scss-lint \(([0-9\.]+, )+[0-9\.]+\)\n$')
    assert ret_re.match(ret)


def test_ruby_get_package_versions():
    def fake_get_versions_str(_):
        return 'scss-lint (0.24.1, 0.24.0, 0.23.1)\n'

    ret = ruby_get_package_versions(
        'scss-lint',
        get_versions_str_fn=fake_get_versions_str,
    )
    # Should be sorted in ascending order
    assert ret == ['0.23.1', '0.24.0', '0.24.1']


def test_format_files_to_directory(tmpdir):
    src_dir = os.path.join(tmpdir.strpath, 'src')
    dest_dir = os.path.join(tmpdir.strpath, 'dest')
    os.mkdir(src_dir)
    os.mkdir(dest_dir)

    # Create some files in src
    def _write_file_in_src(filename, contents):
        with io.open(os.path.join(src_dir, filename), 'w') as file_obj:
            file_obj.write(contents)

    _write_file_in_src('file1.txt', '{foo} bar {baz}')
    _write_file_in_src('file2.txt', 'hello world')
    _write_file_in_src('file3.txt', 'foo bar {baz}')

    format_files_to_directory(
        src_dir, dest_dir, {'foo': 'herp', 'baz': 'derp'},
    )

    def _read_file_in_dest(filename):
        return io.open(os.path.join(dest_dir, filename)).read()

    assert _read_file_in_dest('file1.txt') == 'herp bar derp'
    assert _read_file_in_dest('file2.txt') == 'hello world'
    assert _read_file_in_dest('file3.txt') == 'foo bar derp'


def test_cwd(tmpdir):
    original_cwd = os.getcwd()
    with cwd(tmpdir.strpath):
        assert os.getcwd() == tmpdir.strpath
    assert os.getcwd() == original_cwd


@pytest.yield_fixture
def in_git_dir(tmpdir):
    git_path = os.path.join(tmpdir.strpath, 'gits')
    subprocess.check_call(['git', 'init', git_path])
    with cwd(git_path):
        yield


@pytest.mark.usefixtures('in_git_dir')
def test_apply_version_and_commit():
    _apply_version_and_commit(
        '0.24.1', 'ruby', 'scss-lint', r'\.scss$', 'scss-lint',
    )

    # Assert that our things got copied over
    assert os.path.exists('hooks.yaml')
    assert os.path.exists('__fake_gem.gemspec')
    # Assert that we set the version file correctly
    assert os.path.exists('.version')
    assert io.open('.version').read() == '0.24.1'

    # Assert some things about the gits
    assert get_output('git', 'status', '-s').strip() == ''
    assert get_output('git', 'tag', '-l').strip() == 'v0.24.1'
    assert get_output('git', 'log', '--oneline').strip().split() == [
        mock.ANY, 'Mirror:', '0.24.1',
    ]


def returns_some_versions(_):
    return ['0.23.1', '0.24.0', '0.24.1']


@pytest.mark.usefixtures('in_git_dir')
def test_make_repo_starting_empty():
    make_repo(
        '.', 'ruby', 'scss-lint', r'\.scss$', 'scss-lint',
        version_list_fn_map={'ruby': returns_some_versions},
    )

    # Assert that our things got copied over
    assert os.path.exists('hooks.yaml')
    assert os.path.exists('__fake_gem.gemspec')
    # Assert that we set the version fiel correctly
    assert os.path.exists('.version')
    assert io.open('.version').read() == '0.24.1'

    # Assert some things about hte gits
    assert get_output('git', 'status', '-s').strip() == ''
    assert get_output('git', 'tag', '-l').strip().split() == [
        'v0.23.1', 'v0.24.0', 'v0.24.1',
    ]
    log_lines = get_output('git', 'log', '--oneline').strip().splitlines()
    log_lines_split = [log_line.split() for log_line in log_lines]
    assert log_lines_split == [
        [mock.ANY, 'Mirror:', '0.24.1'],
        [mock.ANY, 'Mirror:', '0.24.0'],
        [mock.ANY, 'Mirror:', '0.23.1'],
    ]


@pytest.mark.usefixtures('in_git_dir')
def test_make_repo_starting_at_version():
    # Write a version file (as if we've already run this before)
    with io.open('.version', 'w') as version_file:
        version_file.write('0.23.1')

    make_repo(
        '.', 'ruby', 'scss-lint', r'\.scss$', 'scss-lint',
        version_list_fn_map={'ruby': returns_some_versions},
    )

    # Assert that we only got tags / commits for the stuff we added
    assert get_output('git', 'tag', '-l').strip().split() == [
        'v0.24.0', 'v0.24.1',
    ]
    log_lines = get_output('git', 'log', '--oneline').strip().splitlines()
    log_lines_split = [log_line.split() for log_line in log_lines]
    assert log_lines_split == [
        [mock.ANY, 'Mirror:', '0.24.1'],
        [mock.ANY, 'Mirror:', '0.24.0'],
    ]
