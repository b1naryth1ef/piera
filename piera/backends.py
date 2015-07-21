import yaml, json
from collections import OrderedDict

class Backend(object):
    """
    Backends provide a way of loading data from files. They should
    override .load with a custom loading method.
    """
    NAME = None

    def __init__(self, parent, obj=None):
        self.parent = parent

        self.obj = obj or {}
        self.datadir = self.obj.get(":datadir", "/etc/puppetlabs/code/environments/%{environment}/hieradata")

    def load(self, data):
        raise NotImplementtedError("Subclasses must implement .load")

class YAMLBackend(Backend):
    NAME = 'yaml'

    def load(self, data):
        return self.load_ordered(data)

    @staticmethod
    def load_ordered(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
        class OrderedLoader(Loader):
            pass

        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return object_pairs_hook(loader.construct_pairs(node))

        OrderedLoader.add_constructor(
                yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                construct_mapping)
        return yaml.load(stream, OrderedLoader)

class JSONBackend(Backend):
    NAME = 'json'

    def load(self, data):
        return json.loads(data, object_pairs_hook=OrderedDict)

