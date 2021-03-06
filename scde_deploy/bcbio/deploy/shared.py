"""Reusable decorators and functions for custom installations.
"""
import os
import time
from contextlib import contextmanager

from fabric.api import *
from fabric.contrib.files import *

# -- decorators and context managers

def _if_not_installed(pname):
    """Decorator that checks if a callable program is installed.
    """
    def argcatcher(func):
        def decorator(*args, **kwargs):
            with settings(
                    hide('warnings', 'running', 'stdout', 'stderr'),
                    warn_only=True):
                result = run(pname)
            if result.return_code == 127:
                return func(*args, **kwargs)
        return decorator
    return argcatcher

def _if_not_python_lib(library):
    """Decorator that checks if a python library is installed.
    """
    def argcatcher(func):
        def decorator(*args, **kwargs):
            with settings(warn_only=True):
                pyver = env.python_version_ext if env.has_key("python_version_ext") else ""
                result = run("python%s -c 'import %s'" % (pyver, library))
            if result.failed:
                return func(*args, **kwargs)
        return decorator
    return argcatcher

@contextmanager
def _make_tmp_dir():
    home_dir = run("echo $HOME")
    work_dir = os.path.join(home_dir, "tmp", "cloudbiolinux")
    if not exists(work_dir):
        run("mkdir -p %s" % work_dir)
    yield work_dir
    if exists(work_dir):
        run("rm -rf %s" % work_dir)

# -- Standard build utility simplifiers

def _get_expected_file(url):
    tar_file = os.path.split(url)[-1]
    tar_file = tar_file.split("?")[0] # remove any extra arguments
    safe_tar = "--pax-option='delete=SCHILY.*,delete=LIBARCHIVE.*'"
    exts = {(".tar.gz", ".tgz") : "tar %s -xzpf" % safe_tar,
            (".tar.bz2",): "tar %s -xjpf" % safe_tar,
            (".zip",) : "unzip"}
    for ext_choices, tar_cmd in exts.iteritems():
        for ext in ext_choices:
            if tar_file.endswith(ext):
                return tar_file, tar_file[:-len(ext)], tar_cmd
    raise ValueError("Did not find extract command for %s" % url)

def _safe_dir_name(dir_name, need_dir=True):
    replace_try = ["", "-src"]
    for replace in replace_try:
        check = dir_name.replace(replace, "")
        if exists(check):
            return check
    # still couldn't find it, it's a nasty one
    first_part = dir_name.split("-")[0].split("_")[0]
    with settings(warn_only=True):
        dirs = run("ls -d1 *%s*/" % first_part).split("\n")
    if len(dirs) == 1:
        return dirs[0]
    if need_dir:
        raise ValueError("Could not find directory %s" % dir_name)

def _fetch_and_unpack(url, need_dir=True):
    if url.startswith(("git", "svn", "hg", "cvs")):
        base = os.path.basename(url.split()[-1])
        dirname = os.path.splitext(base)[0]
        if not exists(dirname):
            run(url)
        return dirname
    else:
        tar_file, dir_name, tar_cmd = _get_expected_file(url)
        if not exists(tar_file):
            run("wget --no-check-certificate -O %s '%s'" % (tar_file, url))
        if not exists(dir_name):
            run("%s %s" % (tar_cmd, tar_file))
        return _safe_dir_name(dir_name, need_dir)

def _configure_make(env):
    run("./configure --prefix=%s " % env.system_install)
    run("make")
    sudo("make install")

def _make_copy(find_cmd=None, premake_cmd=None, do_make=True):
    def _do_work(env):
        if premake_cmd:
            premake_cmd()
        if do_make:
            run("make")
        if find_cmd:
            install_dir = os.path.join(env.system_install, "bin")
            for fname in run(find_cmd).split("\n"):
                sudo("mv -f %s %s" % (fname.rstrip("\r"), install_dir))
    return _do_work

def _get_install(url, env, make_command):
    """Retrieve source from a URL and install in our system directory.
    """
    with _make_tmp_dir() as work_dir:
        with cd(work_dir):
            dir_name = _fetch_and_unpack(url)
            with cd(dir_name):
                make_command(env)

def _get_install_local(url, env, make_command):
    """Build and install in a local directory.
    """
    (_, test_name, _) = _get_expected_file(url)
    test1 = os.path.join(env.local_install, test_name)
    test2, _ = test1.rsplit("-", 1)
    if not exists(test1) and not exists(test2):
        with _make_tmp_dir() as work_dir:
            with cd(work_dir):
                dir_name = _fetch_and_unpack(url)
                if not exists(os.path.join(env.local_install, dir_name)):
                    with cd(dir_name):
                        make_command(env)
                    run("mv %s %s" % (dir_name, env.local_install))

# --- Language specific utilities

def _symlinked_java_version_dir(pname, version):
    base_dir = os.path.join(env.system_install, "share", "java", pname)
    install_dir = "%s-%s" % (base_dir, version)
    if not exists(install_dir):
        sudo("mkdir -p %s" % install_dir)
        if exists(base_dir):
            sudo("rm -f %s" % base_dir)
        sudo("ln -s %s %s" % (install_dir, base_dir))
        return install_dir
    return None

# --- Running servers and daemons

def _is_running(cmd):
    """Check if a given command is currently running.
    """
    with settings(hide('everything')):
        result = run("ps ax | grep '%s'" % cmd)
    is_running = False
    for line in result.split("\n"):
        if line.find(cmd) >= 0 and line.find("grep") == -1:
            is_running = True
            break
    return is_running

def _run_in_screen(name, run_dir, cmd, check_cmd=None, use_sudo=False):
    """Run the given command in a named screen session in the background.

    check_cmd is optional and used to check if the command is running, in cases
    where the running script spawns a process with a different name.
    """
    if check_cmd is None: check_cmd = cmd
    do_run = sudo if use_sudo else run
    send_return = "`echo -ne '\015'`"
    stdout_redirect = ">/dev/null 2>&1"
    if not _is_running(check_cmd):
        with cd(run_dir):
            # Start a detached screen session and then send the command to it
            if use_sudo is False:
                do_run("screen -d -m -S %s %s" % (name, stdout_redirect), pty=False)
            time.sleep(5)
            do_run("screen -S %s -p0 -X stuff '%s'%s %s" % (name, cmd,
                                                            send_return, stdout_redirect))
