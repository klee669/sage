"""
Sage Runtime Environment

AUTHORS:

- \R. Andrew Ohana (2012): Initial version.

"""
########################################################################
#       Copyright (C) 2013 R. Andrew Ohana <andrew.ohana@gmail.com>
#
#  Distributed under the terms of the GNU General Public License (GPL)
#  as published by the Free Software Foundation; either version 2 of
#  the License, or (at your option) any later version.
#
#                  http://www.gnu.org/licenses/
########################################################################
from __future__ import absolute_import

import glob
import os
import socket
import site
from . import version

opj = os.path.join

# set default values for sage environment variables
# every variable can be overwritten by os.environ
SAGE_ENV = dict()

# Helper to build the SAGE_ENV dictionary
def _add_variable_or_fallback(key, fallback, force=False):
    """
    Set ``SAGE_ENV[key]``.

    If ``key`` is an environment variable, this is the
    value. Otherwise, the ``fallback`` is used.

    INPUT:

    - ``key`` -- string.

    - ``fallback`` -- anything.

    - ``force`` -- boolean (optional, default is ``False``). Whether
      to always use the fallback, regardless of environment variables.

    EXAMPLES::

        sage: import os, sage.env
        sage: sage.env.SAGE_ENV = dict()
        sage: os.environ['SAGE_FOO'] = 'foo'
        sage: sage.env._add_variable_or_fallback('SAGE_FOO', '---$SAGE_URL---')
        sage: sage.env.SAGE_FOO
        'foo'
        sage: sage.env.SAGE_ENV['SAGE_FOO']
        'foo'

    If the environment variable does not exist, the fallback is
    used. Previously-declared variables are replaced if they are
    prefixed with a dollar sign::

        sage: _ = os.environ.pop('SAGE_BAR', None)  # ensure that SAGE_BAR does not exist
        sage: sage.env._add_variable_or_fallback('SAGE_BAR', '---$SAGE_FOO---')
        sage: sage.env.SAGE_BAR
        '---foo---'
        sage: sage.env.SAGE_ENV['SAGE_BAR']
        '---foo---'

    Test that :trac:`23758` has been resolved::

        sage: sage.env._add_variable_or_fallback('SAGE_BA', '---hello---')
        sage: sage.env._add_variable_or_fallback('SAGE_QUX', '$SAGE_BAR')
        sage: sage.env.SAGE_ENV['SAGE_QUX']
        '---foo---'
    """
    global SAGE_ENV
    import six
    try:
        import os
        value = os.environ[key]
    except KeyError:
        value = fallback
    if force:
        value = fallback
    if isinstance(value, six.string_types):
        # Now do the variable replacement. First treat 'value' as if
        # it were a path and do the substitution on each of the
        # components. This is to avoid the sloppiness in the second
        # round of substitutions: if VAR and VAR_NEW are both in
        # SAGE_ENV, then when doing substitution on the string
        # "$VAR_NEW/a/b", we want to match VAR_NEW, not VAR, if
        # possible.
        for sep in set([os.path.sep, '/']):
            components = []
            for s in value.split(sep):
                if s.startswith('$'):
                    components.append(SAGE_ENV.get(s[1:], s))
                else:
                    components.append(s)
            value = sep.join(components)
        # Now deal with any remaining substitutions. The following is
        # sloppy, as mentioned above: if $VAR and $VAR_NEW are both in
        # SAGE_ENV, the substitution for "$VAR_NEw" depends on which
        # of the two appears first when iterating over
        # SAGE_ENV.items().
        for k,v in SAGE_ENV.items():
            if isinstance(v, six.string_types):
                value = value.replace('$'+k, v)
    SAGE_ENV[key] = value
    globals()[key] = value

# system info
_add_variable_or_fallback('UNAME',           os.uname()[0])
_add_variable_or_fallback('HOSTNAME',        socket.gethostname())
_add_variable_or_fallback('LOCAL_IDENTIFIER','$HOSTNAME.%s'%os.getpid())

# bunch of sage directories and files
_add_variable_or_fallback('SAGE_ROOT',       None)
_add_variable_or_fallback('SAGE_LOCAL',      None)
_add_variable_or_fallback('SAGE_ETC',        opj('$SAGE_LOCAL', 'etc'))
_add_variable_or_fallback('SAGE_INC',        opj('$SAGE_LOCAL', 'include'))
_add_variable_or_fallback('SAGE_SHARE',      opj('$SAGE_LOCAL', 'share'))

_add_variable_or_fallback('SAGE_SRC',        opj('$SAGE_ROOT', 'src'))

try:
    sitepackages_dirs = site.getsitepackages()
except AttributeError:  # in case of use inside virtualenv
    sitepackages_dirs = [os.path.join(os.path.dirname(site.__file__),
                                     'site-packages')]
_add_variable_or_fallback('SITE_PACKAGES',   sitepackages_dirs)

_add_variable_or_fallback('SAGE_LIB',        SITE_PACKAGES[0])

# Used by sage/misc/package.py.  Should be SAGE_SRC_ROOT in VPATH.
_add_variable_or_fallback('SAGE_PKGS', opj('$SAGE_ROOT', 'build', 'pkgs'))


_add_variable_or_fallback('SAGE_EXTCODE',    opj('$SAGE_SHARE', 'sage', 'ext'))
_add_variable_or_fallback('SAGE_LOGS',       opj('$SAGE_ROOT', 'logs', 'pkgs'))
_add_variable_or_fallback('SAGE_SPKG_INST',  opj('$SAGE_LOCAL', 'var', 'lib', 'sage', 'installed'))
_add_variable_or_fallback('SAGE_DOC_SRC',    opj('$SAGE_SRC', 'doc'))
_add_variable_or_fallback('SAGE_DOC',        opj('$SAGE_SHARE', 'doc', 'sage'))
_add_variable_or_fallback('DOT_SAGE',        opj(os.environ.get('HOME','$SAGE_ROOT'), '.sage'))
_add_variable_or_fallback('SAGE_DOT_GIT',    opj('$SAGE_ROOT', '.git'))
_add_variable_or_fallback('SAGE_DISTFILES',  opj('$SAGE_ROOT', 'upstream'))

# misc
_add_variable_or_fallback('SAGE_URL',                'http://sage.math.washington.edu/sage/')
_add_variable_or_fallback('REALM',                   'sage.math.washington.edu')
_add_variable_or_fallback('TRAC_SERVER_URI',         'https://trac.sagemath.org')
_add_variable_or_fallback('SAGE_REPO_AUTHENTICATED', 'ssh://git@trac.sagemath.org:2222/sage.git')
_add_variable_or_fallback('SAGE_REPO_ANONYMOUS',     'git://trac.sagemath.org/sage.git')
_add_variable_or_fallback('SAGE_VERSION',            version.version)
_add_variable_or_fallback('SAGE_DATE',               version.date)
_add_variable_or_fallback('SAGE_VERSION_BANNER',     version.banner)
_add_variable_or_fallback('SAGE_BANNER',             '')
_add_variable_or_fallback('SAGE_IMPORTALL',          'yes')

# additional packages locations
_add_variable_or_fallback('CONWAY_POLYNOMIALS_DATA_DIR',  opj('$SAGE_SHARE','conway_polynomials'))
_add_variable_or_fallback('GRAPHS_DATA_DIR',  opj('$SAGE_SHARE','graphs'))
_add_variable_or_fallback('ELLCURVE_DATA_DIR',opj('$SAGE_SHARE','ellcurves'))
_add_variable_or_fallback('POLYTOPE_DATA_DIR',opj('$SAGE_SHARE','reflexive_polytopes'))
_add_variable_or_fallback('GAP_ROOT_DIR',     opj('$SAGE_LOCAL','gap','latest'))
_add_variable_or_fallback('THEBE_DIR',        opj('$SAGE_SHARE','thebe'))

# locate singular shared object
if UNAME[:6] == "CYGWIN":
    SINGULAR_SO = ([None] + glob.glob(os.path.join(
        SAGE_LOCAL, "bin", "cygSingular-*.dll")))[-1]
else:
    if UNAME == "Darwin":
        extension = "dylib"
    else:
        extension = "so"
    # library name changed from libsingular to libSingular btw 3.x and 4.x
    SINGULAR_SO = SAGE_LOCAL+"/lib/libSingular."+extension

_add_variable_or_fallback('SINGULAR_SO', SINGULAR_SO)

if not SINGULAR_SO or not os.path.exists(SINGULAR_SO):
    raise RuntimeError(
        "libSingular not found--a working Singular install in $SAGE_LOCAL "
        "is required for Sage to work")

# post process
if ' ' in DOT_SAGE:
    if UNAME[:6] == 'CYGWIN':
        # on windows/cygwin it is typical for the home directory
        # to have a space in it.  Fortunately, users also have
        # write privileges to c:\cygwin\home, so we just put
        # .sage there.
        _add_variable_or_fallback('DOT_SAGE', "/home/.sage", force=True)
    else:
        print("Your home directory has a space in it.  This")
        print("will probably break some functionality of Sage.  E.g.,")
        print("the GAP interface will not work. A workaround")
        print("is to set the environment variable HOME to a")
        print("directory with no spaces that you have write")
        print("permissions to before you start sage.")


CYGWIN_VERSION = None
if UNAME[:6] == 'CYGWIN':
    import re
    _uname = os.uname()
    if len(_uname) >= 2:
        m = re.match(r'(\d+\.\d+\.\d+)\(.+\)', _uname[2])
        if m:
            CYGWIN_VERSION = tuple(map(int, m.group(1).split('.')))

        del m
    del _uname, re

# things that need DOT_SAGE
_add_variable_or_fallback('PYTHON_EGG_CACHE',   opj('$DOT_SAGE', '.python-eggs'))
_add_variable_or_fallback('SAGE_STARTUP_FILE',  opj('$DOT_SAGE', 'init.sage'))

# delete temporary variables used for setting up sage.env
del opj, os, socket, version, site

def sage_include_directories(use_sources=False):
    """
    Return the list of include directories for compiling Sage extension modules.

    INPUT:

    -  ``use_sources`` -- (default: False) a boolean

    OUTPUT:

    a list of include directories to be used to compile sage code
    1. while building sage (use_sources='True')
    2. while using sage (use_sources='False')

    EXAMPLES:

    Expected output while using sage

    ::

        sage: import sage.env
        sage: sage.env.sage_include_directories()
        ['.../include',
        '.../include/python...',
        '.../python.../numpy/core/include',
        '.../python.../site-packages',
        '.../python.../site-packages/sage/ext']
    """
    import os, numpy
    import distutils.sysconfig

    opj = os.path.join

    include_directories = [SAGE_INC,
                           distutils.sysconfig.get_python_inc(),
                           numpy.get_include()]

    if use_sources :
        include_directories.extend([SAGE_SRC,
                                    opj(SAGE_SRC, 'sage', 'ext')])
    else:
        include_directories.extend([SAGE_LIB,
                                    opj(SAGE_LIB, 'sage', 'ext')])

    return include_directories


def cython_aliases():
    """
    Return the aliases for compiling Cython code. These aliases are
    macros which can occur in ``# distutils`` headers.

    EXAMPLES::

        sage: from sage.env import cython_aliases
        sage: cython_aliases()
        {...}
        sage: sorted(cython_aliases().keys())
        ['FFLASFFPACK_CFLAGS',
         'FFLASFFPACK_INCDIR',
         'FFLASFFPACK_LIBDIR',
         'FFLASFFPACK_LIBRARIES',
         'GIVARO_CFLAGS',
         'GIVARO_INCDIR',
         'GIVARO_LIBDIR',
         'GIVARO_LIBRARIES',
         'GSL_CFLAGS',
         'GSL_INCDIR',
         'GSL_LIBDIR',
         'GSL_LIBRARIES',
         'LINBOX_CFLAGS',
         'LINBOX_INCDIR',
         'LINBOX_LIBDIR',
         'LINBOX_LIBRARIES',
         'SINGULAR_CFLAGS',
         'SINGULAR_INCDIR',
         'SINGULAR_LIBDIR',
         'SINGULAR_LIBRARIES']
    """
    import pkgconfig

    aliases = {}

    for lib in ['fflas-ffpack', 'givaro', 'gsl', 'linbox', 'Singular']:
        var = lib.upper().replace("-", "") + "_"
        aliases[var + "CFLAGS"] = pkgconfig.cflags(lib).split()
        pc = pkgconfig.parse(lib)
        # INCDIR should be redundant because the -I options are also
        # passed in CFLAGS
        aliases[var + "INCDIR"] = pc['include_dirs']
        aliases[var + "LIBDIR"] = pc['library_dirs']
        aliases[var + "LIBRARIES"] = pc['libraries']

    # LinBox needs special care because it actually requires C++11 with
    # GNU extensions: -std=c++11 does not work, you need -std=gnu++11
    # (this is true at least with GCC 7.2.0).
    #
    # Further, note that LinBox does not add any C++11 flag in its .pc
    # file (possibly because of confusion between CFLAGS and CXXFLAGS?).
    # This is not a problem in practice since LinBox depends on
    # fflas-ffpack and fflas-ffpack does add such a C++11 flag.
    aliases["LINBOX_CFLAGS"].append("-std=gnu++11")

    return aliases
