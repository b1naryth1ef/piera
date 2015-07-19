import re, os, yaml
from collections import OrderedDict

lookup = re.compile(r'''%\{(scope|hiera|literal|alias)\(['"]([^"']*)["']\)\}''')

def yaml_load_ordered(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))

    OrderedLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_mapping)
    return yaml.load(stream, OrderedLoader)

class Hiera(object):
    """
    The Hiera object represents a first-class interaction between Python and
    Hiera data. It takes a base-hiera config YAML file, and exposes methods
    to retrieve and fully resolve Hiera data.

    :param base_file: The Hiera base configuration file
    :param context: Any additional kwargs will be passed in as a base context.
    """
    def __init__(self, base_file, **context):
        self.base_file = base_file
        self.context = context

        self.cache = {}
        self.paths =  []

        self.load()

    def load(self):
        """
        Attempts to fully load a Hiera base configuration. This must be called before
        attempting to lookup values.
        """
        self.base = yaml_load_ordered(open(self.base_file))
        self.backend = self.base[':backends'][0]
        self.data_dir = os.path.join(os.path.dirname(self.base_file), self.base[':' + self.backend][':datadir'])
        self.hierarchy = []
       
        # Load our heirarchy
        for path in self.base[':hierarchy']:
            self.hierarchy.append(re.sub("%{([a-zA-Z_-|\d]+)}", "{\g<1>}", path, count=0))

        # Now pre-load/cache a bunch of global stuff. If context vars where provided
        #  in the constructor, we'll also load those files into the cache.
        self.get(None)

    def load_directory(self, path):
        """
        Attempts to load all yaml files in a directory
        """
        result = []
        for root, dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".yaml"):
                    result.append(self.load_file(os.path.join(root, f)))
        return result

    def load_file(self, path, ignore_cache=False):
        """
        Attempts to load a single yaml file
        """
        if path not in self.cache or ignore_cache:
            self.cache[path] = yaml_load_ordered(open(path).read().decode('utf8'))
        return path

    def resolve_function(self, s, paths, context):
        """
        Fully resolve a hiera function call
        """
        opt, arg = lookup.findall(s)[0]

        if opt == 'hiera':
            return self.get_key(arg, paths, context)
        elif opt == 'scope':
            return context.get(arg)
        else:
            raise Exception("Unsupported hiera function: %s" % opts[0][0])

    def resolve_dict(self, obj, paths, context):
        """
        Fully resolve hiera function calls within a dictionary
        """
        new_obj = OrderedDict()
        for k, v in obj.iteritems():
            if isinstance(v, dict):
                new_obj[k] = self.resolve_dict(v, paths, context)
            elif isinstance(v, str) and lookup.match(v):
                new_obj[k] = self.resolve_function(v, paths, context)
            else:
                new_obj[k] = v
        return new_obj

    def get_key(self, key, paths, context):
        """
        Get the value of a key within hiera
        """
        for path in paths:
            if key in self.cache[path]:
                value = self.cache[path][key]
                
                if isinstance(value, str) and lookup.match(value):
                    # If we're a hiera function call, lets resolve ourselves
                    return self.resolve_function(value, paths, context)
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

        # First, we need to resolve a list of valid paths, in order and load them
        paths = []
        for h in self.hierarchy:
            try:
                path = os.path.join(self.data_dir, h.format(**ctx))
            except KeyError:
                continue

            if os.path.isdir(path):
                paths += self.load_directory(path)
            else:
                if os.path.exists(path + '.yaml'):
                    paths.append(self.load_file(path + '.yaml'))
        
        # Locate the value, or fail and return the default
        return self.get_key(key, paths, ctx) or default

