import re, os
from collections import OrderedDict

from .backends import YAMLBackend, JSONBackend

function = re.compile(r'''%\{(scope|hiera|literal|alias)\(['"]([^"']*)["']\)\}''')
interpolate = re.compile(r'''%\{([^\}]*)\}''')

class Hiera(object):
    """
    The Hiera object represents a first-class interaction between Python and
    Hiera data. It takes a base-hiera config YAML file, and exposes methods
    to retrieve and fully resolve Hiera data.

    :param base_file: The Hiera base configuration file path or file-like object
    :param backends: A list of backends to use for loading, by default this is
        YAMLBackend and JSONBackend
    :param context: Any additional kwargs will be passed in as a base context.
    """
    def __init__(self, base_file, backends=None, **context):
        self.base_file = base_file
        self.context = context

        self.cache = {}
        self.paths =  []

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

        if not self.base:
            raise Exception("Failed to parse base Hiera configuration")

        # Load all backends
        self.backends = {}
        for backend in self.base[':backends']:
            obj = filter(lambda i: i.NAME == backend, backends)
            if not len(obj):
                raise Exception("Invalid Backend: `{}`".format(backend))
            self.backends[backend] = obj[0](self, self.base.get(":{}".format(backend)))

        # Make sure we have at least a single backend
        if not len(self.backends):
            raise Exception("No backends could be loaded")

        self.hierarchy = []

        if not ':hierarchy' in self.base:
            raise Exception("Invalid Base Hiera Config: missing hierarchy key")

        # Load our heirarchy
        for path in self.base[':hierarchy']:
            self.hierarchy.append(re.sub("%{([a-zA-Z_-|\d]+)}", "{\g<1>}", path, count=0))

        # Now pre-load/cache a bunch of global stuff. If context vars where provided
        #  in the constructor, we'll also load those files into the cache.
        self.get(None)

    def load_directory(self, path, backend=None):
        """
        Walks an entire directory and attempts to load all relevant data files
        based on our backends. Optionally can only load for one backend.
        """
        for root, dirs, files in os.walk(path):
            for f in files:
                backend = backend or self.backends.get(':{}'.format(os.path.splitext(f)[-1]))
                if backend:
                    yield self.load_file(os.path.join(root, f), backend)

    def load_file(self, path, backend, ignore_cache=False):
        """
        Attempts to load a file for a specific backend, caching the result.
        """
        if path not in self.cache or ignore_cache:
            try:
                self.cache[path] = backend.load(open(path).read().decode('utf8'))
            except Exception as e:
                raise Exception("Failed to load file {}: `{}`".format(path, e))
        return path

    def can_resolve(self, s):
        """
        Returns true if any resolving or interpolation can be done on the provided
        string
        """
        if isinstance(s, str) and (function.findall(s) or interpolate.findall(s)):
            return True
        return False

    def resolve_function(self, s, paths, context):
        """
        Attempts to fully resolve a hiera function call within a value. This includes
        interpolation for relevant calls.
        """
        calls = function.findall(s)
        
        # If this is an alias, just replace it (doesn't require interpolation)
        if len(calls) == 1 and calls[0][0] == 'alias':
            if function.sub("", s) != "":
                raise Exception("Alias can not be used for string interpolation: `{}`".format(s))
            return self.get_key(calls[0][1], paths, context)

        # Iterate over all function calls and string interpolate their resolved values
        for call, arg in calls:
            if call == 'hiera':
                replace = self.get_key(arg, paths, context)
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
            s = interpolate.sub(context.get(i), s, 1)

        return s

    def resolve(self, s, paths, context):
        """
        Fully resolves a string, including function and interpolation based resolving.
        """
        base = self.resolve_function(s, paths, context)

        # If we can string interpolate the result, lets do that
        if isinstance(base, str):
            base = self.resolve_interpolates(base, context)

        return base

    def resolve_dict(self, obj, paths, context):
        """
        Recursively and completely resolves all Hiera interoplates/functions
        within a dictionary.
        """
        new_obj = OrderedDict()
        for k, v in obj.iteritems():
            if isinstance(v, dict):
                new_obj[k] = self.resolve_dict(v, paths, context)
            elif self.can_resolve(v):
                new_obj[k] = self.resolve(v, paths, context)
            else:
                new_obj[k] = v
        return new_obj

    def get_key(self, key, paths, context):
        """
        Get the value of a key within hiera, resolving if required
        """
        for path in paths:
            if self.cache[path] is not None and key in self.cache[path]:
                value = self.cache[path][key]

                if self.can_resolve(value):
                    # If we're a hiera function call, lets resolve ourselves
                    return self.resolve(value, paths, context)
                elif isinstance(value, dict):
                    # If we're a dict, we need to resolve internal function calls
                    return self.resolve_dict(value, paths, context)
                else:
                    return value

    def get(self, key, default=None, **kwargs):
        """
        Attempts to retrieve a hiera variable by fully resolving its location.

        :param key: They Hiera key to retrieve
        :param default: If the Hiera key is not found, return this value
        :param kwargs: Any kwargs passed will override context-variables.
        """
        ctx = self.context.copy()
        ctx.update(kwargs)
        ctx = {k: v for k, v in ctx.items() if v}

        # First, we need to resolve a list of valid paths, in order and load them
        paths = []

        for backend in self.backends.values():
            for path in self.hierarchy:
                try:
                    path = os.path.join(self.base_path, backend.datadir, path.format(**ctx))
                except KeyError: continue

                if os.path.isdir(path):
                    paths += list(self.load_directory(path, backend))
                elif os.path.exists(path +  '.' + backend.NAME):
                    paths.append(self.load_file(path + '.' + backend.NAME, backend))

        # Locate the value, or fail and return the default
        return self.get_key(key, paths, ctx) or default

