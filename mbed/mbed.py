#!/usr/bin/env python

# Copyright (c) 2016-2019 Arm Limited, All Rights Reserved
# SPDX-License-Identifier: Apache-2.0

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied.


# pylint: disable=too-many-arguments, too-many-locals, too-many-branches, too-many-lines, line-too-long,
# pylint: disable=too-many-nested-blocks, too-many-public-methods, too-many-instance-attributes, too-many-statements
# pylint: disable=invalid-name, missing-docstring, bad-continuation

from __future__ import print_function

try:
    # Python 2
    basestring = (unicode, str)
    from urlparse import urlparse
    from urllib2 import urlopen
    from urllib import quote
except NameError:
    # Python 3
    basestring = str
    from urllib.parse import urlparse, quote
    from urllib.request  import urlopen

import traceback
import sys
import re
import subprocess
import os
import json
import platform
import contextlib
import shutil
import stat
import errno
import ctypes
from itertools import chain, repeat
import time
import zipfile
import argparse
from random import randint
from contextlib import contextmanager


# Application version
ver = '1.10.4'

# Default paths to Mercurial and Git
hg_cmd = 'hg'
git_cmd = 'git'

# override python command when running standalone Mbed CLI
python_cmd = sys.executable
if os.path.basename(python_cmd).startswith('mbed'):
    python_cmd = 'python'

ignores = [
    # Version control folders
    ".hg",
    ".git",
    ".svn",
    ".CVS",
    ".cvs",

    # Version control fallout
    "*.orig",

    # mbed Tools
    "BUILD",
    ".build",
    ".export",

    # Online IDE caches
    ".msub",
    ".meta",
    ".ctags*",

    # uVision project files
    "*.uvproj",
    "*.uvopt",

    # Eclipse project files
    "*.project",
    "*.cproject",
    "*.launch",

    # IAR project files
    "*.ewp",
    "*.eww",

    # GCC make
    "/Makefile",
    "Debug",

    # HTML files
    "*.htm",

    # Settings files
    ".mbed",
    "*.settings",
    "mbed_settings.py",

    # Python
    "*.py[cod]",
    "# subrepo ignores",
    ]

# git & url (no #rev)
regex_repo_url = r'^(git\://|file\://|ssh\://|https?\://|)(([^/:@]+)(\:([^/:@]+))?@)?([^/:]{3,})(\:\d+)?[:/](.+?)(\.git|\.hg|\/?)$'
# mbed url is subset of hg. mbed doesn't support ssh transport though so https? urls cannot be converted to ssh
regex_mbed_url = r'^(https?)://(([^/:@]+)(\:([^/:@]+))?@)?([\w\-\.]*mbed\.(co\.uk|org|com))(\:\d+)?[:/](.+?)/?$'
# mbed sdk builds url are treated specially
regex_build_url = r'^(https?://([\w\-\.]*mbed\.(co\.uk|org|com))/(users|teams)/([\w\-]{1,32})/(repos|code)/([\w\-]+))/builds/?([\w\-]{6,40}|tip)?/?$'

# valid .lib reference to local (unpublished) repo - dir#rev
regex_local_ref = r'^([\w.+-][\w./+-]*?)/?(?:#(.*))?$'
# valid .lib reference to repo - url#rev
regex_url_ref = r'^(.*/([\w.+-]+)(?:\.\w+)?)/?(?:#(.*))?$'

# match official release tags
regex_rels_official = r'^(release|rel|mbed-os|[rv]+)?[.-]?\d+(\.\d+)*$'
# match rc/beta/alpha release tags
regex_rels_all = r'^(release|rel|mbed-os|[rv]+)?[.-]?\d+(\.\d+)*([a-z0-9.-]+)?$'

# base url for all mbed related repos (used as sort of index)
mbed_base_url = 'https://github.com/ARMmbed'
# default mbed OS url
mbed_os_url = 'https://github.com/ARMmbed/mbed-os'
# default mbed library url
mbed_lib_url = 'https://mbed.org/users/mbed_official/code/mbed/builds/'
# mbed SDK tools needed for programs based on mbed SDK library
mbed_sdk_tools_url = 'https://mbed.org/users/mbed_official/code/mbed-sdk-tools'

# a list of public SCM service (github/butbucket) which support http, https and ssh schemas
public_scm_services = ['bitbucket.org', 'github.com', 'gitlab.com']

# commands that don't get the current work path shown
skip_workpath_commands = ["config", "cfg", "conf"]

# verbose logging
verbose = False
very_verbose = False
install_requirements = True
cache_repositories = True

mbed_app_file_name = "mbed_app.json"

# stores current working directory for recursive operations
cwd_root = ""
_cwd = os.getcwd()

# Logging and output
def log(msg, is_error=False):
    sys.stderr.write(msg) if is_error else sys.stdout.write(msg)

def message(msg):
    if very_verbose:
        return "[mbed-%s] %s\n" % (os.getpid(), msg)
    else:
        return "[mbed] %s\n" % msg

def info(msg, level=1):
    if level <= 0 or verbose:
        for line in msg.splitlines():
            log(message(line))

def action(msg):
    for line in msg.splitlines():
        log(message(line))

def warning(msg):
    pass

def error(msg, code=-1):
    lines = msg.splitlines()
    log(message("ERROR: %s" % lines.pop(0)), True)
    for line in lines:
        log("       %s\n" % line, True)
    log("---\n", True)
    sys.exit(code)

def offline_warning(offline, top=True):
    pass

def progress_cursor():
    while True:
        for cursor in '|/-\\':
            yield cursor

progress_spinner = progress_cursor()

def progress():
    pass

def show_progress(title, percent, max_width=80):
    pass

def hide_progress(max_width=80):
    pass

def create_default_mbed_app():
    # Default data content
    pass

# Process execution
class ProcessException(Exception):
    pass


def popen(command, **kwargs):
    # print for debugging
    pass

def pquery(command, output_callback=None, stdin=None, **kwargs):
    if very_verbose:
        info("Exec \"%s\" in \"%s\"" % (' '.join(command), getcwd()))
    try:
        proc = subprocess.Popen(command, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    except OSError as e:
        if e.args[0] == errno.ENOENT:
            error(
                "Could not execute \"%s\" in \"%s\".\n"
                "You can verify that it's installed and accessible from your current path by executing \"%s\".\n" % (' '.join(command), getcwd(), command[0]), e.args[0])
        else:
            raise e

    if output_callback:
        line = ""
        while 1:
            s = str(proc.stderr.read(1))
            line += s
            if s == '\r' or s == '\n':
                output_callback(line, s)
                line = ""

            if proc.returncode is None:
                proc.poll()
            else:
                break

    stdout, _ = proc.communicate(stdin)

    if very_verbose:
        log(stdout.decode(sys.getfilesystemencoding()).strip() + "\n")

    if proc.returncode != 0:
        raise ProcessException(proc.returncode, command[0], ' '.join(command), getcwd())

    return stdout.decode(sys.getfilesystemencoding())

def rmtree_readonly(directory):
    pass

def sizeof_fmt(num, suffix='B'):
    pass

# Directory navigation
@contextlib.contextmanager
def cd(newdir):
    global _cwd
    prevdir = getcwd()
    os.chdir(newdir)
    _cwd = newdir
    try:
        yield
    finally:
        os.chdir(prevdir)
        _cwd = prevdir

def getcwd():
    global _cwd
    return _cwd

def relpath(root, path):
    return path[len(root)+1:]


def staticclass(cls):
    pass


# Handling for multiple version controls
scms = {}
def scm(name):
    def _scm(cls):
        pass
    return _scm

# pylint: disable=no-self-argument, no-method-argument, no-member, no-self-use, unused-argument
@scm('bld')
@staticclass
class Bld(object):
    name = 'bld'
    default_branch = 'default'

    def init(path):
        pass

    def cleanup():
        pass

    def clone(url, path=None, depth=None, protocol=None):
        pass

    def fetch_rev(url, rev):
        pass

    def unpack_rev(rev):
        pass

    def checkout(rev, clean=False):
        pass

    def update(rev=None, clean=False, clean_files=False, is_local=False):
        pass

    def untracked():
        pass

    def isvalidurl(url):
        return re.match(regex_build_url, url.strip().replace('\\', '/'))

    def seturl(url):
        pass

    def geturl():
        with open(os.path.join('.bld', 'bldrc')) as f:
            url = f.read().strip()
        m = Bld.isvalidurl(url)
        return m.group(1)+'/builds' if m else ''

    def getrev():
        pass

    def getbranch():
        pass

    def gettags(rev=None):
        pass


# pylint: disable=no-self-argument, no-method-argument, no-member, no-self-use, unused-argument
@scm('hg')
@staticclass
class Hg(object):
    name = 'hg'
    default_branch = 'default'
    ignore_file = os.path.join('.hg', 'hgignore')

    def init(path=None):
        pass

    def cleanup():
        pass

    def clone(url, name=None, depth=None, protocol=None):
        pass

    def add(dest):
        pass

    def remove(dest):
        pass

    def commit(msg=None):
        pass

    def publish(all_refs=None):
        pass

    def fetch():
        pass

    def discard():
        pass

    def checkout(rev, clean=False, clean_files=False):
        pass

    def update(rev=None, clean=False, clean_files=False, is_local=False):
        pass

    def status():
        pass

    def dirty():
        pass

    def untracked():
        pass

    def outgoing():
        pass

    def seturl(url):
        pass

    def geturl():
        tagpaths = '[paths]'
        default_url = ''
        url = ''

        try:
            with open(os.path.join('.hg', 'hgrc')) as f:
                lines = f.read().splitlines()
                if tagpaths in lines:
                    idx = lines.index(tagpaths)
                    m = re.match(r'^([\w_]+)\s*=\s*(.*)$', lines[idx+1])
                    if m:
                        if m.group(1) == 'default':
                            default_url = m.group(2)
                        else:
                            url = m.group(2)
        except IOError:
            pass

        if default_url:
            url = default_url

        return formaturl(url or pquery([hg_cmd, 'paths', 'default']).strip())

    def getrev():
        pass

    def getbranch():
        pass

    def gettags():
        pass

    def remoteid(url, rev=None):
        pass

    def hgrc():
        pass

    def ignores():
        pass

    def ignore(dest):
        pass

    def unignore(dest):
        pass

    def action_progress(line, sep):
        pass


# pylint: disable=no-self-argument, no-method-argument, no-member, no-self-use, unused-argument
@scm('git')
@staticclass
class Git(object):
    name = 'git'
    default_branch = 'master'
    ignore_file = os.path.join('.git', 'info', 'exclude')

    def init(path=None):
        pass

    def cleanup():
        pass

    def clone(url, name=None, depth=None, protocol=None):
        pass

    def add(dest):
        pass

    def remove(dest):
        pass

    def commit(msg=None):
        pass

    def publish(all_refs=None):
        pass

    def fetch():
        pass

    def discard(clean_files=False):
        pass

    def merge(dest):
        pass

    def checkout(rev, clean=False):
        pass

    def update(rev=None, clean=False, clean_files=False, is_local=False):
        pass

    def status():
        pass

    def dirty():
        pass

    def untracked():
        pass

    def outgoing():
        # Get default remote
        pass

    # Checks whether current working tree is detached
    def isdetached():
        pass

    # Finds default remote
    def getremote():
        pass

    # Finds all associated remotes for the specified remote type
    def getremotes(rtype='fetch'):
        result = []
        remotes = pquery([git_cmd, 'remote', '-v']).strip().splitlines()
        for remote in remotes:
            remote = re.split(r'\s', remote)
            t = re.sub('[()]', '', remote[2])
            if not rtype or rtype == t:
                result.append([remote[0], remote[1], t])
        return result

    def seturl(url):
        pass

    def geturl():
        url = ""
        remotes = Git.getremotes()
        for remote in remotes:
            url = remote[1]
            if remote[0] == "origin": # Prefer origin URL
                break
        return formaturl(url)

    def getrev():
        pass

    # Gets current branch or returns empty string if detached
    def getbranch(rev='HEAD'):
        pass

    # Get all refs
    def getrefs():
        pass

    # Finds branches (local or remote). Will match rev if specified
    def getbranches(rev=None, ret_rev=False):
        pass

    # Finds tags. Will match rev if specified
    def gettags():
        pass

    # Finds branches a rev belongs to
    def revbranches(rev):
        pass

    def ignores():
        pass

    def ignore(dest):
        pass
    def unignore(dest):
        pass

    def action_progress(line, sep):
        pass

_environment_markers = {
    "platform_system": platform.system()
}

_comparators = {
    "!=": lambda a, b: a != b,
    "==": lambda a, b: a == b,
}

def _eval_environment_marker(marker):
    pass

# Repository object
class Repo(object):
    is_local = False
    is_build = False
    name = None
    path = None
    url = None
    rev = None
    scm = None
    libs = []
    cache = None

    @classmethod
    def fromurl(cls, url, path=None):
        repo = cls()
        m_local = re.match(regex_local_ref, url.strip().replace('\\', '/'))
        m_repo_ref = re.match(regex_url_ref, url.strip().replace('\\', '/'))
        m_bld_ref = re.match(regex_build_url, url.strip().replace('\\', '/'))
        if m_local:
            repo.name = os.path.basename(path or m_local.group(1))
            repo.path = os.path.abspath(path or os.path.join(getcwd(), m_local.group(1)))
            repo.url = m_local.group(1)
            repo.rev = m_local.group(2)
            repo.is_local = True
        elif m_bld_ref:
            repo.name = os.path.basename(path or m_bld_ref.group(7))
            repo.path = os.path.abspath(path or os.path.join(getcwd(), repo.name))
            repo.url = m_bld_ref.group(1)+'/builds'
            repo.rev = m_bld_ref.group(8)
            repo.is_build = True
        elif m_repo_ref:
            repo.name = re.sub(r'\.(git|hg)/?$', '', os.path.basename(path or m_repo_ref.group(2)))
            repo.path = os.path.abspath(path or os.path.join(getcwd(), repo.name))
            repo.url = formaturl(m_repo_ref.group(1))
            repo.rev = m_repo_ref.group(3)
        else:
            error('Invalid repository (%s)' % url.strip(), -1)

        cache_cfg = Global().cache_cfg()
        if cache_repositories and cache_cfg['cache'] == 'enabled':
            repo.cache = cache_cfg['cache_dir']

        return repo

    @classmethod
    def fromlib(cls, lib=None):
        pass

    @classmethod
    def fromrepo(cls, path=None):
        pass

    @classmethod
    def isrepo(cls, path=None):
        for name, _ in scms.items():
            if os.path.isdir(os.path.join(path, '.'+name)):
                return True

        return False

    @classmethod
    def findparent(cls, path=None):
        path = os.path.abspath(path or getcwd())

        while cd(path):
            if os.path.isfile(os.path.join(path, Cfg.file)) or Repo.isrepo(path):
                return path

            tpath = path
            path = os.path.split(path)[0]
            if tpath == path:
                break

        return None

    @classmethod
    def pathtype(cls, path=None):
        path = os.path.abspath(path or getcwd())

        depth = 0
        while cd(path):
            tpath = path
            path = Repo.findparent(path)
            if path:
                depth += 1
                path = os.path.split(path)[0]
                if tpath == path:       # Reached root.
                    break
            else:
                break

        return "directory" if depth == 0 else ("program" if depth == 1 else "library")

    def revtype(self, rev=None, ret_type=True, ret_rev=True, fmt=3):
        pass

    @classmethod
    def isurl(cls, url):
        pass

    @classmethod
    def isinsecure(cls, url):
        pass

    @property
    def lib(self):
        pass

    @property
    def fullurl(self):
        pass

    def sync(self):
        pass

    def getscm(self):
        pass

    def gettags(self, rev=None):
        pass

    # Pass backend SCM commands and parameters if SCM exists
    def __wrap_scm(self, method):
        pass

    def __getattr__(self, attr):
        pass

    def remove(self, dest, *args, **kwargs):
        pass

    def clone(self, url, path, rev=None, depth=None, protocol=None, offline=False, **kwargs):
        # Sorted so repositories that match urls are attempted first
        pass

    def getlibs(self):
        pass

    def write(self):
        up = urlparse(self.url)
        if up.hostname:
            url = up._replace(netloc=up.hostname + (':'+str(up.port) if up.port else '')).geturl() # strip auth string
        else:
            url = self.url # use local repo "urls" as is

        if os.path.isfile(self.lib):
            with open(self.lib) as f:
                lib_repo = Repo.fromurl(f.read().strip())
                if (formaturl(lib_repo.url, 'https') == formaturl(url, 'https') # match URLs in common schema (https)
                        and (lib_repo.rev == self.rev                           # match revs, even if rev is None (valid for repos with no revisions)
                             or (lib_repo.rev and self.rev
                                 and lib_repo.rev == self.rev[0:len(lib_repo.rev)]))):  # match long and short rev formats
                    #print self.name, 'unmodified'
                    return

        if up.hostname in public_scm_services:
            # Safely convert repo URL to https schema if this is a public SCM service (github/butbucket), supporting all schemas.
            # This allows anonymous cloning of public repos without having to have ssh keys and associated accounts at github/bitbucket/etc.
            # Without this anonymous users will get clone errors with ssh repository links even if the repository is public.
            # See https://help.github.com/articles/which-remote-url-should-i-use/
            url = formaturl(url, 'https')

        ref = url.rstrip('/') + '/' + (('' if self.is_build else '#') + self.rev if self.rev else '')
        action("Updating reference \"%s\" -> \"%s\"" % (relpath(cwd_root, self.path) if cwd_root != self.path else self.name, ref))
        with open(self.lib, 'w') as f:
            f.write(ref+"\n")

    def rm_untracked(self):
        pass

    def url2cachedir(self, url):
        pass

    def get_cache(self, url, scm):
        pass

    def set_cache(self, url):
        pass

    def cache_lock(self, url):
        pass

    def cache_unlock(self, url):
        pass

    @contextmanager
    def cache_lock_held(self, url):
        pass

    def pid_exists(self, pid):
        pass

    def can_update(self, clean, clean_deps):
        pass

    def check_repo(self, show_warning=None):
        pass


# Program class, acts code base root
class Program(object):
    path = None
    name = None
    is_cwd = False
    is_repo = False
    is_classic = False
    build_dir = "BUILD"

    def __init__(self, path=None, print_warning=False):
        pass

    def get_cfg(self, *args, **kwargs):
        return Cfg(self.path).get(*args, **kwargs) or Global().get_cfg(*args, **kwargs)

    def set_cfg(self, *args, **kwargs):
        return Cfg(self.path).set(*args, **kwargs)

    def list_cfg(self, *args, **kwargs):
        pass

    def set_root(self):
        pass

    def unset_root(self, path=None):
        pass

    # Gets mbed OS dir (unified)
    def get_os_dir(self):
        pass

    def get_mbedlib_dir(self):
        pass

    # Gets mbed tools dir (unified)
    def get_tools_dir(self):
        pass

    def get_requirements(self):
        pass

    def _find_file_paths(self, paths, fl):
        pass

    def requirements_contains(self, library_name):
        pass

    def check_requirements(self, require_install=False):
        pass


    # Routines after cloning mbed-os
    def post_action(self, check_reqs=True):
        pass

    def add_tools(self, path):
        pass

    def update_tools(self, path):
        pass

    def get_tools(self):
        pass

    def get_env(self):
        pass

    def get_target(self, target=None):
        pass

    def get_toolchain(self, toolchain=None):
        pass

    def get_profile(self, profile=None):
        pass

    def set_defaults(self, target=None, toolchain=None):
        if target and not self.get_cfg('TARGET'):
            self.set_cfg('TARGET', target)
        if toolchain and not self.get_cfg('TOOLCHAIN'):
            self.set_cfg('TOOLCHAIN', toolchain)

    def get_macros(self, more_macros=None):
        pass


    def ignore_build_dir(self):
        pass

    def detect_single_target(self, info=None):
        pass

    def get_detected_targets(self):
        pass


# Global class used for global config
class Global(object):
    def __init__(self):
        pass

    def get_cfg(self, *args, **kwargs):
        return Cfg(self.path).get(*args, **kwargs)

    def set_cfg(self, *args, **kwargs):
        return Cfg(self.path).set(*args, **kwargs)

    def list_cfg(self, *args, **kwargs):
        pass

    def cache_cfg(self, *args, **kwargs):
        return Cfg(self.path).cache(*args, **kwargs)


# Cfg classed used for handling the config backend
class Cfg(object):
    path = None
    file = ".mbed"

    def __init__(self, path):
        self.path = path

    # Sets config value
    def set(self, var, val):
        pass

    # Gets config value
    def get(self, var, default_val=None):
        fl = os.path.join(self.path, self.file)
        try:
            with open(fl) as f:
                lines = f.read().splitlines()
        except (IOError, OSError):
            lines = []

        for line in lines:
            m = re.match(r'^([\w+-]+)\=(.*)$', line)
            if m and m.group(1) == var:
                return m.group(2)
        return default_val

    # Get all config var/values pairs
    def list(self):
        pass

    # Get cache configuration
    def cache(self):
        cache_cfg = self.get('CACHE', 'enabled')
        cache_val = 'enabled' if cache_repositories and cache_cfg and cache_cfg != 'none' and cache_cfg != 'off' and cache_cfg != 'disabled' else 'disabled'

        cache_dir_cfg = self.get('CACHE_DIR', None)
        loc = cache_dir_cfg if cache_dir_cfg != 'default' else (cache_cfg if (cache_cfg and cache_cfg != 'on' and cache_cfg != 'off' and cache_cfg != 'none' and cache_cfg != 'enabled' and cache_cfg != 'disabled') else None)
        cache_base = loc or Global().path
        return {'cache': cache_val, 'cache_base': cache_base, 'cache_dir': os.path.join(cache_base, 'mbed-cache')}


def formaturl(url, format="default"):
    url = "%s" % url
    m = re.match(regex_mbed_url, url)
    if m:
        if format == "http": # mbed urls doesn't convert to ssh - only http and https
            url = 'http://%s%s%s/%s' % (m.group(2) or '', m.group(6), m.group(8) or '', m.group(9))
        else:
            url = 'https://%s%s%s/%s' % (m.group(2) or '', m.group(6), m.group(8) or '', m.group(9))
    else:
        m = re.match(regex_repo_url, url)
        if m and m.group(1) == '': # no protocol specified, probably ssh string like "git@github.com:ARMmbed/mbed-os.git"
            url = 'ssh://%s%s%s/%s' % (m.group(2) or 'git@', m.group(6), m.group(7) or '', m.group(8)) # convert to common ssh URL-like format
            m = re.match(regex_repo_url, url)

        if m:
            if format == "ssh":
                url = 'ssh://%s%s%s/%s' % (m.group(2) or 'git@', m.group(6), m.group(7) or '', m.group(8))
            elif format == "http":
                url = 'http://%s%s%s/%s' % (m.group(2) if (m.group(2) and (m.group(5) or m.group(3) != 'git')) else '', m.group(6), m.group(7) or '', m.group(8))
            elif format == "https":
                url = 'https://%s%s%s/%s' % (m.group(2) if (m.group(2) and (m.group(5) or m.group(3) != 'git')) else '', m.group(6), m.group(7) or '', m.group(8))
    return url

# Wrapper for the MbedTermnal functionality
def mbed_sterm(port, baudrate=9600, echo=True, reset=False, sterm=False):
    pass


# Subparser handling
parser = argparse.ArgumentParser(prog='mbed',
    description="Command-line code management tool for ARM mbed OS - http://www.mbed.com\nversion %s\n\nUse \"mbed <command> -h|--help\" for detailed help.\nOnline manual and guide available at https://github.com/ARMmbed/mbed-cli" % ver,
    formatter_class=argparse.RawTextHelpFormatter)
subparsers = parser.add_subparsers(title="Commands", metavar="           ")
parser.add_argument("--version", action="store_true", dest="version", help="print version number and exit")
subcommands = {}

# Process handling
def subcommand(name, *args, **kwargs):
    def __subcommand(command):
        pass
    return __subcommand


# New command
@subcommand('new',
    dict(name='name', help='Destination name or path'),
    dict(name='--scm', nargs='?', help='Source control management. Currently supported: %s. Default: git' % ', '.join([s.name for s in scms.values()])),
    dict(name='--program', action='store_true', help='Force creation of an mbed program. Default: auto.'),
    dict(name='--library', action='store_true', help='Force creation of an mbed library. Default: auto.'),
    dict(name='--mbedlib', action='store_true', help='Add the mbed library instead of mbed-os into the program.'),
    dict(name='--create-only', action='store_true', help='Only create a program, do not import mbed-os or mbed library.'),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch the mbed OS repository when creating new program. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol when fetching the mbed OS repository when creating new program. Supported: https, http, ssh, git. Default: inferred from URL.'),
    dict(name='--offline', action='store_true', help='Offline mode will force the use of locally cached repositories and prevent requests to remote repositories.'),
    dict(name='--no-requirements', action='store_true', help='Disables checking for and installing any requirements.'),
    help='Create new mbed program or library',
    description=(
        "Creates a new mbed program if executed within a non-program location.\n"
        "Alternatively creates an mbed library if executed within an existing program.\n"
        "When creating new program, the latest mbed-os release will be downloaded/added\n unless --create-only is specified.\n"
        "Supported source control management: git, hg"))
def new(name, scm='git', program=False, library=False, mbedlib=False, create_only=False, depth=None, protocol=None, offline=False, no_requirements=False):
    pass


# Import command
@subcommand('import',
    dict(name='url', help='URL of the program'),
    dict(name='path', nargs='?', help='Destination name or path. Default: current directory.'),
    dict(name=['-I', '--ignore'], action='store_true', help='Ignore errors related to cloning and updating.'),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    dict(name='--insecure', action='store_true', help='Allow insecure repository URLs. By default mbed CLI imports only "safe" URLs, e.g. based on standard ports - 80, 443 and 22. This option enables the use of arbitrary URLs/ports.'),
    dict(name='--offline', action='store_true', help='Offline mode will force the use of locally cached repositories and prevent requests to remote repositories.'),
    dict(name='--no-requirements', action='store_true', help='Disables checking for and installing any requirements.'),
    hidden_aliases=['im', 'imp'],
    help='Import program from URL',
    description=(
        "Imports mbed program and its dependencies from a source control based URL\n"
        "(GitHub, Bitbucket, mbed.org) into the current directory or specified\npath.\n"
        "Use \"mbed add <URL>\" to add a library into an existing program."))
def import_(url, path=None, ignore=False, depth=None, protocol=None, insecure=False, offline=False, no_requirements=False, top=True):
    pass


# Add library command
@subcommand('add',
    dict(name='url', help='URL of the library'),
    dict(name='path', nargs='?', help='Destination name or path. Default: current folder.'),
    dict(name=['-I', '--ignore'], action='store_true', help='Ignore errors related to cloning and updating.'),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    dict(name='--insecure', action='store_true', help='Allow insecure repository URLs. By default mbed CLI imports only "safe" URLs, e.g. based on standard ports - 80, 443 and 22. This option enables the use of arbitrary URLs/ports.'),
    dict(name='--offline', action='store_true', help='Offline mode will force the use of locally cached repositories and prevent requests to remote repositories.'),
    dict(name='--no-requirements', action='store_true', help='Disables checking for and installing any requirements.'),
    hidden_aliases=['ad'],
    help='Add library from URL',
    description=(
        "Adds mbed library and its dependencies from a source control based URL\n"
        "(GitHub, Bitbucket, mbed.org) into an existing program.\n"
        "Use \"mbed import <URL>\" to import as a program"))
def add(url, path=None, ignore=False, depth=None, protocol=None, insecure=False, offline=False, no_requirements=False, top=True):
    pass


# Remove library
@subcommand('remove',
    dict(name='path', help='Local library name or path'),
    help='Remove library',
    hidden_aliases=['rm', 'rem'],
    description=(
        "Remove specified library, its dependencies and references from the current\n"
        "You can re-add the library from its URL via \"mbed add <URL>\"."))
def remove(path):
    pass


# Deploy command
@subcommand('deploy',
    dict(name=['-I', '--ignore'], action='store_true', help='Ignore errors related to cloning and updating.'),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    dict(name='--insecure', action='store_true', help='Allow insecure repository URLs. By default mbed CLI imports only "safe" URLs, e.g. based on standard ports - 80, 443 and 22. This option enables the use of arbitrary URLs/ports.'),
    dict(name='--offline', action='store_true', help='Offline mode will force the use of locally cached repositories and prevent requests to remote repositories.'),
    dict(name='--no-requirements', action='store_true', help='Disables checking for and installing any requirements.'),
    help='Find and add missing libraries',
    description=(
        "Import missing dependencies in an existing program or library.\n"
        "Hint: Use \"mbed import <URL>\" and \"mbed add <URL>\" instead of cloning\n"
        "manually and then running \"mbed deploy\""))
def deploy(ignore=False, depth=None, protocol=None, insecure=False, offline=False, no_requirements=False, top=True):
    pass

# Publish command
@subcommand('publish',
    dict(name=['-A', '--all'], dest='all_refs', action='store_true', help='Publish all branches, including new ones. Default: push only the current branch.'),
    dict(name=['-M', '--message'], dest='msg', type=str, nargs='?', help='Commit message. Default: prompts for commit message.'),
    hidden_aliases=['pub'],
    help='Publish program or library',
    description=(
        "Publishes the current program or library and all dependencies to their\nassociated remote repository URLs.\n"
        "This command performs various consistency checks for local uncommitted changes\n"
        "and unpublished revisions and encourages to commit/push them.\n"
        "Online guide about collaboration is available at:\n"
        "www.mbed.com/collab_guide"))
def publish(all_refs=None, msg=None, top=True):
    pass


# Update command
@subcommand('update',
    dict(name='rev', nargs='?', help='Revision, tag or branch'),
    dict(name=['-C', '--clean'], action='store_true', help='Perform a clean update and discard all modified or untracked files. WARNING: This action cannot be undone. Use with caution.'),
    dict(name='--clean-files', action='store_true', help='Remove any local ignored files. Requires \'--clean\'. WARNING: This will wipe all local uncommitted, untracked and ignored files. Use with extreme caution.'),
    dict(name='--clean-deps', action='store_true', help='Remove any local libraries and also libraries containing uncommitted or unpublished changes. Requires \'--clean\'. WARNING: This action cannot be undone. Use with caution.'),
    dict(name=['-I', '--ignore'], action='store_true', help='Ignore errors related to unpublished libraries, unpublished or uncommitted changes, and attempt to update from associated remote repository URLs.'),
    dict(name='--depth', nargs='?', help='Number of revisions to fetch from the remote repository. Default: all revisions.'),
    dict(name='--protocol', nargs='?', help='Transport protocol for the source control management. Supported: https, http, ssh, git. Default: inferred from URL.'),
    dict(name='--insecure', action='store_true', help='Allow insecure repository URLs. By default mbed CLI imports only "safe" URLs, e.g. based on standard ports - 80, 443 and 22. This option enables the use of arbitrary URLs/ports.'),
    dict(name='--offline', action='store_true', help='Offline mode will force the use of locally cached repositories and prevent requests to remote repositories.'),
    dict(name=['-l', '--latest-deps'], action='store_true', help='Update all dependencies to the latest revision of their current branch. WARNING: Ignores lib files'),
    dict(name='--no-requirements', action='store_true', help='Disables checking for and installing any requirements.'),
    hidden_aliases=['up'],
    help='Update to branch, tag, revision or latest',
    description=(
        "Updates the current program or library and its dependencies to specified\nbranch, tag or revision.\n"
        "Alternatively fetches from associated remote repository URL and updates to the\n"
        "latest revision in the current branch."))
def update(rev=None, clean=False, clean_files=False, clean_deps=False, ignore=False, depth=None, protocol=None, insecure=False, offline=False, latest_deps=False, no_requirements=False, top=True):
    pass


# Synch command
@subcommand('sync',
    help='Synchronize library references\n\n',
    description=(
        "Synchronizes all library and dependency references (.lib files) in the\n"
        "current program or library.\n"
        "Note that this will remove all invalid library references."))
def sync(recursive=True, keep_refs=False, top=True):
    pass


# List command
@subcommand('ls',
    dict(name=['-a', '--all'], dest='detailed', action='store_true', help='List repository URL and revision pairs'),
    dict(name=['-I', '--ignore'], action='store_true', help='Ignore errors related to missing libraries.'),
    help='View dependency tree',
    description=(
        "View the dependency tree of the current program or library."))
def list_(detailed=False, prefix='', p_path=None, ignore=False):
    pass


# Command release for cross-SCM release tags of repositories
@subcommand('releases',
    dict(name=['-a', '--all'], dest='detailed', action='store_true', help='Show revision hashes'),
    dict(name=['-u', '--unstable'], dest='unstable', action='store_true', help='Show unstable releases well, e.g. release candidates, alphas, betas, etc'),
    dict(name=['-r', '--recursive'], action='store_true', help='Show release tags for all libraries and sub-libraries as well'),
    hidden_aliases=['rel', 'rels'],
    help='Show release tags',
    description=(
        "Show release tags for the current program or library."))
def releases_(detailed=False, unstable=False, recursive=False, prefix='', p_path=None):
    pass


# Command status for cross-SCM status of repositories
@subcommand('status',
    dict(name=['-I', '--ignore'], action='store_true', help='Ignore errors related to missing libraries.'),
    hidden_aliases=['st', 'stat'],
    help='Show version control status\n\n',
    description=(
        "Show uncommitted changes a program or library and its dependencies."))
def status_(ignore=False):
    pass


# Helper function for compile and test subcommands
def _safe_append_profile_to_build_path(build_path, profile):
    pass


# Compile command which invokes the mbed OS native build system
@subcommand('compile',
    dict(name=['-t', '--toolchain'], help='Compile toolchain. Example: ARM, GCC_ARM, IAR'),
    dict(name=['-m', '--target'], help='Compile target MCU. Example: K64F, NUCLEO_F401RE, NRF51822...'),
    dict(name=['-D', '--macro'], action='append', help='Add a macro definition'),
    dict(name=['--profile'], action='append', help='Path of a build profile configuration file (or name of Mbed OS profile). Default: develop'),
    dict(name='--library', dest='compile_library', action='store_true', help='Compile the current program or library as a static library.'),
    dict(name='--config', dest='compile_config', action='store_true', help='Show run-time compile configuration'),
    dict(name='--prefix', dest='config_prefix', action='append', help='Restrict listing to parameters that have this prefix'),
    dict(name='--source', action='append', help='Source directory. Default: . (current dir)'),
    dict(name='--build', help='Build directory. Default: build/'),
    dict(name=['-c', '--clean'], action='store_true', help='Clean the build directory before compiling'),
    dict(name=['-f', '--flash'], action='store_true', help='Flash the built firmware onto a connected target.'),
    dict(name=['--sterm'], action='store_true', help='Open serial terminal after compiling. Can be chained with --flash'),
    dict(name=['--baudrate'], help='Serial terminal communication baudrate. Default: 9600'),
    dict(name=['-N', '--artifact-name'], help='Name of the built program or library'),
    dict(name=['-S', '--supported'], dest='supported', const=True, choices=["matrix", "toolchains", "targets"], nargs="?", help='Shows supported matrix of targets and toolchains'),
    dict(name='--app-config', dest="app_config", help="Path of an application configuration file. Default is to look for \"mbed_app.json\"."),
    help='Compile code using the mbed build tools',
    description="Compile this program using the mbed build tools.")
def compile_(toolchain=None, target=None, macro=False, profile=False,
             compile_library=False, compile_config=False, config_prefix=None,
             source=False, build=False, clean=False, flash=False, sterm=False,
             baudrate=9600, artifact_name=None, supported=False, app_config=None):
    # Gather remaining arguments
    pass


# Test command
@subcommand('test',
    dict(name=['-t', '--toolchain'], help='Compile toolchain. Example: ARM, GCC_ARM, IAR'),
    dict(name=['-m', '--target'], help='Compile target MCU. Example: K64F, NUCLEO_F401RE, NRF51822...'),
    dict(name=['-D', '--macro'], action='append', help='Add a macro definition'),
    dict(name='--compile-list', dest='compile_list', action='store_true',
         help='List all tests that can be built'),
    dict(name='--run-list', dest='run_list', action='store_true', help='List all built tests that can be ran'),
    dict(name='--compile', dest='compile_only', action='store_true', help='Only compile tests'),
    dict(name='--run', dest='run_only', action='store_true', help='Only run tests'),
    dict(name=['-n', '--tests-by-name'], dest='tests_by_name',
         help='Limit the tests to a list (ex. test1,test2,test3)'),
    dict(name='--source', action='append', help='Source directory. Default: . (current dir)'),
    dict(name='--build', help='Build directory. Default: build/'),
    dict(name=['--profile'], action='append',
         help='Path of a build profile configuration file (or name of Mbed OS profile). Default: develop'),
    dict(name=['-c', '--clean'], action='store_true', help='Clean the build directory before compiling'),
    dict(name='--test-spec', dest="test_spec", help="Path used for the test spec file used when building and running tests (the default path is the build directory)"),
    dict(name='--app-config', dest="app_config", help="Path of an application configuration file. Default is to look for \"mbed_app.json\""),
    dict(name='--test-config', dest="test_config", help="Path or mbed OS keyword of a test configuration file. Example: ethernet, odin_wifi, or path/to/config.json"),
    dict(name='--coverage', choices=['html', 'xml', 'both'], help='Generate code coverage report for unit tests'),
    dict(name='--valgrind', action='store_true', help='Use Valgrind for unit tests'),
    dict(name=['--make-program'], choices=['gmake', 'make', 'mingw32-make', 'ninja'], help='Which make program to use for unit tests'),
    dict(name=['--generator'], choices=['Unix Makefiles', 'MinGW Makefiles', 'Ninja'], help='Which CMake generator to use for unit tests'),
    dict(name='--new', help='generate files for a new unit test', metavar="FILEPATH"),
    dict(name=['-r', '--regex'], help='Run unit tests matching regular expression'),
    dict(name=['--unittests'], action="store_true", help='Run only unit tests'),
    dict(name='--build-data', dest="build_data", default=None, help="Dump build_data to this file"),
    dict(name=['--greentea'], dest="greentea", action='store_true', default=False, help="Run Greentea tests"),
    dict(name=['--icetea'], dest="icetea", action='store_true', default=False,
         help="Run Icetea tests. If used without --greentea flag then run only icetea tests."),
    help='Find, build and run tests',
    description="Find, build, and run tests in a program and libraries")
def test_(toolchain=None, target=None, macro=False, compile_list=False, run_list=False, compile_only=False, run_only=False, tests_by_name=None, source=False, profile=False, build=False, clean=False, test_spec=None, app_config=None, test_config=None, coverage=None, valgrind=None, make_program=None, new=None, generator=None, regex=None, unittests=None, build_data=None, greentea=None, icetea=None):

    # Default behaviour is to run only greentea tests
    pass


# device management commands
@subcommand('device-management',
    dict(name=['-t', '--toolchain'], help='Toolchain used for mbed compile'),
    dict(name=['-m', '--target'], help='Target used for compile for target MCU. Example: K64F, NUCLEO_F401RE, NRF51822...'),
    dict(name=['--profile'], help=""),
    dict(name='--build', help='Build directory. Default: build/'),
    dict(name='--source', action='append', help='Source directory. Default: . (current dir)'),
    help='device management subcommand',
    add_help=False,
    hidden_aliases=['dev-mgmt', 'dm'],
    description=("Manage Device with Pelion"))
def dev_mgmt(toolchain=None, target=None, source=False, profile=False, build=False):
    pass

# Export command
@subcommand('export',
    dict(name=['-i', '--ide'], help='IDE to create project files for. Example: UVISION4, UVISION5, GCC_ARM, IAR, COIDE'),
    dict(name=['-m', '--target'], help='Export for target MCU. Example: K64F, NUCLEO_F401RE, NRF51822...'),
    dict(name='--source', action='append', help='Source directory. Default: . (current dir)'),
    dict(name=['--profile'], action='append', help='Path of a build profile configuration file (or name of Mbed OS profile). Default: debug'),
    dict(name=['-c', '--clean'], action='store_true', help='Clean the build directory before compiling'),
    dict(name=['-S', '--supported'], dest='supported', const=True, choices=['matrix', 'ides'], nargs='?', help='Shows supported matrix of targets and toolchains'),
    dict(name='--app-config', dest="app_config", help="Path of an application configuration file. Default is to look for \"mbed_app.json\""),
    dict(name='--no-requirements', action='store_true', help='Disables checking for and installing any requirements.'),
    help='Generate an IDE project',
    description=(
        "Generate IDE project files for the current program."))
def export(ide=None, target=None, source=False, profile=["debug"], clean=False, supported=False, app_config=None, no_requirements=False):
    # Gather remaining arguments
    pass


# Detect command
@subcommand('detect',
    hidden_aliases=['det'],
    help='Detect connected Mbed targets/boards\n\n',
    description=(
        "Detect Mbed targets/boards connected to this system and show supported\n"
        "toolchain matrix."))
def detect():
    # Gather remaining arguments
    pass


# Serial terminal command
@subcommand('sterm',
    dict(name=['-m', '--target'], help='Compile target MCU. Example: K64F, NUCLEO_F401RE, NRF51822...'),
    dict(name=['-p', '--port'], help='Communication port. Default: auto-detect. Specifying this will also ignore the -m/--target option above.'),
    dict(name=['-b', '--baudrate'], help='Communication baudrate. Default: 9600'),
    dict(name=['-e', '--echo'], help='Switch local echo on/off. Default: on'),
    dict(name=['-r', '--reset'], action='store_true', help='Reset the targets (via SendBreak) before opening terminal.'),
    hidden_aliases=['term'],
    help='Open serial terminal to connected target.\n\n',
    description=(
        "Open serial terminal to connected target (usually board), or connect to a user-specified COM port\n"))
def sterm(target=None, port=None, baudrate=None, echo=None, reset=False, sterm=True):
    # Gather remaining arguments
    pass

# Generic config command
@subcommand('config',
    dict(name='var', nargs='?', help='Variable name. E.g. "target", "toolchain", "protocol"'),
    dict(name='value', nargs='?', help='Value. Will show the currently set default value for a variable if not specified.'),
    dict(name=['-G', '--global'], dest='global_cfg', action='store_true', help='Use global settings, not local'),
    dict(name=['-U', '--unset'], dest='unset', action='store_true', help='Unset the specified variable.'),
    dict(name=['-L', '--list'], dest='list_config', action='store_true', help='List mbed tool configuration. Not to be confused with compile configuration, e.g. "mbed compile --config".'),
    hidden_aliases=['cfg', 'conf'],
    help='Tool configuration',
    description=(
        "Gets, sets or unsets mbed tool configuration options.\n"
        "Options can be global (via the --global switch) or local (per program)\n"
        "Global options are always overridden by local/program options.\n"
        "Currently supported options: target, toolchain, protocol, depth, cache, profile, color"))
def config_(var=None, value=None, global_cfg=False, unset=False, list_config=False):
    pass


# Build system and exporters
@subcommand('target',
    dict(name='name', nargs='?', help='Default target name. Example: K64F, NUCLEO_F401RE, NRF51822...'),
    dict(name=['-G', '--global'], dest='global_cfg', action='store_true', help='Use global settings, not local'),
    dict(name=['-S', '--supported'], dest='supported', action='store_true', help='Shows supported matrix of targets and toolchains'),
    help='Set or get default target',
    description=(
        "Set or get default toolchain\n"
        "This is an alias to \"mbed config [--global] target [name]\"\n"))
def target_(name=None, global_cfg=False, supported=False):
    pass


@subcommand('toolchain',
    dict(name='name', nargs='?', help='Default toolchain name. Example: ARM, GCC_ARM, IAR'),
    dict(name=['-G', '--global'], dest='global_cfg', action='store_true', help='Use global settings, not local'),
    dict(name=['-S', '--supported'], dest='supported', action='store_true', help='Shows supported matrix of targets and toolchains'),
    help='Set or get default toolchain',
    description=(
        "Set or get default toolchain\n"
        "This is an alias to \"mbed config [--global] toolchain [name]\"\n"))
def toolchain_(name=None, global_cfg=False, supported=False):
    pass


@subcommand('cache',
    dict(name='on', nargs='?', help='Turn repository caching on. Will use either the default or the user specified cache directory.'),
    dict(name='off', nargs='?', help='Turn repository caching off. Note that this doesn\'t purge cached repositories. See "purge".'),
    dict(name='dir', nargs='?', help='Set cache directory. Set to "default" to let mbed CLI determine the cache directory location (%s/mbed-cache/).' % Global().path),
    dict(name='ls', nargs='?', help='List cached repositories and their sizes.'),
    dict(name='purge', nargs='?', help='Purge cached repositories. Note that this doesn\'t turn caching off'),
    help='Repository cache management\n\n',
    description=(
        "Repository cache management\n"
        "To minimize traffic and reduce import times, Mbed CLI can cache repositories by storing their indexes.\n"
        "By default repository caching is turned on. Turn it off if you experience any problems.\n"))
def cache_(on=False, off=False, dir=None, ls=False, purge=False, global_cfg=False):
    pass


@subcommand('help',
    help='This help screen')
def help_():
    return parser.print_help()



def main():
    global verbose, very_verbose, remainder, cwd_root

    # Help messages adapt based on current dir
    cwd_root = getcwd()

    # Parse/run command
    if len(sys.argv) <= 1:
        help_()
        sys.exit(1)

    if '--version' in sys.argv:
        log(ver+"\n")
        sys.exit(0)

    pargs, remainder = parser.parse_known_args()
    status = 1

    very_verbose = pargs.very_verbose
    verbose = very_verbose or pargs.verbose
    try:
        pathtype = Repo.pathtype(cwd_root)
        if not sys.argv[1].lower() in skip_workpath_commands:
            action('Working path \"%s\" (%s)' % (cwd_root, pathtype))
            if pathtype == "library":
                action('Program path \"%s\"' % Program(cwd_root).path)
        status = pargs.command(pargs)
    except ProcessException as e:
        tip = "" if verbose else "\nTip: You could retry the last command with \"-v\" flag for verbose output\n"

        error(
            "\"%s\" returned error.\n"
            "Code: %d\n"
            "Path: \"%s\"\n"
            "Command: \"%s\"%s" % (e.args[1], e.args[0], e.args[3], e.args[2], tip))
    except OSError as e:
        if e.args[0] == errno.ENOENT:
            error(
                "Could not detect one of the command-line tools.\n"
                "You could retry the last command with \"-v\" flag for verbose output\n", e.args[0])
        else:
            error('OS Error: %s' % e.args[1], e.args[0])
    except KeyboardInterrupt:
        info('User aborted!', -1)
        sys.exit(255)
    except Exception as e:
        if very_verbose:
            traceback.print_exc(file=sys.stdout)
        error("Unknown Error: %s" % e, 255)

    sys.exit(status or 0)


if __name__ == "__main__":
    main()
