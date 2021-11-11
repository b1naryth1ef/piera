import os
import re
import sys
from collections import OrderedDict

from .backends import YAMLBackend, JSONBackend

function = re.compile(r'''%\{(scope|hiera|literal|alias)\(['"](?:::|)([^"']*)["']\)\}''')
interpolate = re.compile(r'''%\{(?:::|)([^\}]*)\}''')
rformat = re.compile(r'''%{(?:::|)([a-zA-Z_-|\d]+)}''')
PY3 = sys.version_info >= (3, 0)

if PY3:
    string_types = (str, )
else:
    string_types = (str, unicode)


class Merge(object):
    def __init__(self, typ, deep=False):
        self.typ = typ
        self.deep = deep

        if typ == dict:
            self.value = OrderedDict()
        else:
            self.value = typ()

        if deep:
            raise Exception("Deep merging isn't supported yet!")

    def merge_value(self, value):
        if isinstance(self.value, list):
            self.value += list(value)
        elif isinstance(self.value, set):
            self.value = self.value | set(value)
        elif isinstance(self.value, dict):
            for k, v in (value.items() if PY3 else value.iteritems()):
                if k not in self.value:
                    self.value[k] = v
        else:
            raise TypeError("Cannot handle merge_value of type %s", type(self.value))


class ScopedHiera(object):
    def __init__(self, hiera, context=None):
        self.hiera = hiera
        self.context = context or {}

    def has(self, key, **kwargs):
        kwargs.update(self.context)
        return self.hiera.has(key, **kwargs)

    def get(self, key, default=None, merge=None, merge_deep=False, throw=False, context=None, **kwargs):
        new_context = {}
        new_context.update(self.context)
        new_context.update(context or {})
        new_context.update(kwargs)
        return self.hiera.get(key, default, merge, merge_deep, throw, new_context)

    def __getattr__(self, name):
        if hasattr(self.hiera, name):
            return getattr(self.hiera, name)
        raise AttributeError


class Hiera(object):
    """
    The Hiera object represents a first-class interaction between Python and
    Hiera data. It takes a base-hiera config YAML file, and exposes methods
    to retrieve and fully resolve Hiera data.

    :param base_file: The Hiera base configuration file path or file-like object
    :param version: The Hiera file version to expect. Default: 3 for backwards compatibility
    :param always_resolve: Allow resolve to skip values that aren't present. Default: False - breaks backwards compatibility
    :param backends: A list of backends to use for loading, by default this is
        YAMLBackend and JSONBackend
    :param context: Any dictionary of format/context variables to default for the
        liftime of this instance.
    :param kwargs: Any additional kwargs will be added to the context
    """
    def __init__(self, base_file, version=5, always_resolve=False, backends=None, context=None, **kwargs):
        self.version = version
        self.always_resolve = always_resolve
        self.base_file = base_file
        self.context = context or {}
        self.context.update(kwargs)

        self.cache = {}
        self.paths = []

        self.load(backends or [YAMLBackend, JSONBackend])

    def load(self, backends):
        """
        This function loads the base Hiera configuration, attempting to parse and
        build state based on it. This will raise exceptions if the loading process
        fails due to invalid configuration.
        """

        # If we don't have a file-like object, attempt to open as a file path
        if not hasattr(self.base_file, 'read'):
            self.base_path = os.path.dirname(self.base_file)
            self.base_file = open(self.base_file)
        else:
            self.base_path = os.getcwd()

        # Load our base YAML configuration
        self.base = YAMLBackend.load_ordered(self.base_file)
        self.base_file.close()

        if not self.base:
            raise Exception("Failed to parse base Hiera configuration")

        # Detect keys by version
        hierarchy_key = ':hierarchy' if self.version == 3 else 'hierarchy'
        backends_list = self.base[':backends'] if self.version == 3 else ['yaml']

        # Load all backends
        self.backends = OrderedDict()
        for backend in backends_list:
            obj = [i for i in backends if i.NAME == backend]
            if not len(obj):
                raise Exception("Invalid Backend: `{}`".format(backend))
            backend_key = ":{}".format(backend) if self.version == 3 else 'defaults'
            self.backends[backend] = obj[0](self, self.base.get(backend_key))

        # Make sure we have at least a single backend
        if not len(self.backends):
            raise Exception("No backends could be loaded")

        self.hierarchy = []

        if hierarchy_key not in self.base:
            raise Exception("Invalid Base Hiera Config: missing hierarchy key")

        # Load our heirarchy
        for path in self.base[hierarchy_key]:
            path_key = path
            if hasattr(path, 'path'):
                path_key = path.path
            if isinstance(path, dict):
                if 'path' in path:
                    path_key = path['path']
                elif 'name' in path:
                    path_key = path['name']
                else:
                    path_key = None
            hierarchy_key = rformat.sub("{\g<1>}", path_key, count=0)
            self.hierarchy.append(hierarchy_key)

        # Load our backends
        for backend in self.backends.values():
            backend.datadir = rformat.sub("{\g<1>}", backend.datadir, count=0)

        # Now pre-load/cache a bunch of global stuff. If context vars where provided
        #  in the constructor, we'll also load those files into the cache.
        self.get(None)

    def load_directory(self, path, backend=None):
        """
        Walks an entire directory and attempts to load all relevant data files
        based on our backends. Optionally can only load for one backend.
        """
        for root, dirs, files in os.walk(path):
            for file_path in files:
                ext = os.path.splitext(file_path)[-1]
                if backend and ext not in backend.EXTS:
                    continue
                else:
                    backend = self.backends.get(':{}'.format(ext))
                    if not backend:
                        continue

                yield self.load_file(os.path.join(root, file_path), backend)

    def load_file(self, path, backend, ignore_cache=False):
        """
        Attempts to load a file for a specific backend, caching the result.
        """
        if path not in self.cache or ignore_cache:
            try:
                with open(path) as fobj:
                    raw_data = fobj.read()

                if not PY3:
                    raw_data = raw_data.decode('utf8')
                self.cache[path] = backend.load(raw_data)
            except Exception as e:
                raise Exception("Failed to load file {}: `{}`".format(path, e))
        return path

    def can_resolve(self, s):
        """
        Returns true if any resolving or interpolation can be done on the provided
        string
        """
        if isinstance(s, string_types) and (function.findall(s) or interpolate.findall(s)):
            return True
        return False

    def resolve_function(self, s, paths, context, merge):
        """
        Attempts to fully resolve a hiera function call within a value. This includes
        interpolation for relevant calls.
        """
        calls = function.findall(s)

        # If this is an alias, just replace it (doesn't require interpolation)
        if len(calls) == 1 and calls[0][0] == 'alias':
            if function.sub("", s) != "":
                raise Exception("Alias can not be used for string interpolation: `{}`".format(s))
            return self.get_key(calls[0][1], paths, context, None)

        # Iterate over all function calls and string interpolate their resolved values
        for call, arg in calls:
            if call == 'hiera':
                replace = self.get_key(arg, paths, context, None)
            elif call == 'scope':
                replace = context.get(arg)
            elif call == 'literal':
                replace = arg
            elif call == 'alias':
                raise Exception("Invalid alias function call: `{}`".format(s))

            if not replace:
                raise Exception("Could not resolve value for function call: `{}`".format(s))

            if not isinstance(replace, str):
                raise Exception("Resolved value is not a string for function call: `{}`".format(s))

            # Replace only the current function call with our resolved value
            s = function.sub(replace, s, 1)

        return s

    def resolve_interpolates(self, s, context):
        """
        Attempts to resolve context-based string interpolation
        """
        interps = interpolate.findall(s)

        for i in interps:
            if self.always_resolve or self.can_resolve(i):
                s = interpolate.sub(context.get(i), s, 1)

        return s

    def resolve(self, s, paths, context, merge):
        """
        Fully resolves an object, including function and interpolation based resolving.
        """
        if isinstance(s, dict):
            return self.resolve_dict(s, paths, context, merge)
        elif isinstance(s, list):
            return list(self.resolve_list(s, paths, context, merge))
        elif not self.can_resolve(s):
            return s

        base = self.resolve_function(s, paths, context, merge)

        # If we can string interpolate the result, lets do that
        if isinstance(base, str):
            base = self.resolve_interpolates(base, context)

        return base

    def resolve_dict(self, obj, paths, context, merge):
        """
        Recursively and completely resolves all Hiera interoplates/functions
        within a dictionary.
        """
        new_obj = OrderedDict()
        for k, v in (obj.items() if PY3 else obj.iteritems()):
            new_obj[k] = self.resolve(v, paths, context, merge)
        return new_obj

    def resolve_list(self, obj, paths, context, merge):
        for item in obj:
            yield self.resolve(item, paths, context, merge)

    def get_key(self, key, paths, context, merge):
        """
        Get the value of a key within hiera, resolving if required
        """
        for path in paths:
            if self.cache[path] is not None and key in self.cache[path]:
                value = self.resolve(self.cache[path][key], paths, context, (merge if merge and merge.deep else merge))

                if merge:
                    merge.merge_value(value)
                else:
                    return value

        if merge and merge.value:
            return merge.value

        raise KeyError(key)

    def scoped(self, context=None, **kwargs):
        context = context or {}
        context.update(kwargs)
        return ScopedHiera(self, context)

    def has(self, key, **kwargs):
        """
        Returns true if the key exists in hiera, false otherwise
        """
        try:
            self.get(key, throw=True, **kwargs)
            return True
        except KeyError:
            return False

    def get(self, key, default=None, merge=None, merge_deep=False, throw=False, context=None, **kwargs):
        """
        Attempts to retrieve a hiera variable by fully resolving its location.

        :param key: They Hiera key to retrieve
        :param default: If the Hiera key is not found, return this value
        :param merge: If set to a list or dictionary, will perform a array or hash
            merge accordingly.
        :param throw: If true, will ignore default and throw KeyError on a missing
            key.
        :param context: A dictionary of key-value pairs to be passed in as context
            variables.
        :param kwargs: Any kwargs passed will override context-variables.
        """
        new_context = {}
        new_context.update(self.context)
        new_context.update(context or {})
        new_context.update(kwargs)

        # Filter None values
        new_context = {k: v for k, v in new_context.items() if v}

        # First, we need to resolve a list of valid paths, in order and load them
        paths = []

        for backend in self.backends.values():
            for path in self.hierarchy:
                try:
                    path = os.path.join(
                        self.base_path,
                        backend.datadir.format(**new_context),
                        path.format(**new_context))
                except KeyError:
                    continue

                if os.path.isdir(path):
                    paths.extend(list(self.load_directory(path, backend)))
                elif os.path.exists(path):
                    paths.append(self.load_file(path, backend))
                elif os.path.exists(path + '.' + backend.NAME):
                    paths.append(self.load_file(path + '.' + backend.NAME, backend))

        if merge:
            merge = Merge(merge, merge_deep)

        # Locate the value, or fail and return the defaults
        try:
            return self.get_key(key, paths, new_context, merge=merge)
        except KeyError:
            if throw:
                raise
            return default

    def get_nested(self, keyName):
        keyParts = keyName.split('.')

        value = None

        for i in range(0, len(keyParts)):
            keyPartName = keyParts[i]

            if i == 0:
                #if self.has(keyPartName):
                value = self.get(keyPartName)
            elif isinstance(value, dict) and keyPartName in value:
                value = value[keyPartName]
            else:
                value = None

        return value

    def get_and_assert(self, keyName, expectedValue, result_func=None):
        print ('Getting: %s, expecting: %s%s' % (keyName, expectedValue, "" if result_func is None else " (after conversion func)"))

        value = self.get_nested(keyName)

        if result_func != None:
            value = result_func(value)

        assert value == expectedValue, "'%s' was: '%s', expected: '%s'" % (keyName, value, expectedValue)
