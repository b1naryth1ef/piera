import os
import tempfile
import unittest
import piera

try:
    import StringIO
except ImportError:
    import io as StringIO

data_filename = 'v5_hiera.yaml'
current_dirname, _ = os.path.split(os.path.abspath(__file__))


class BaseTestPiera(unittest.TestCase):
    def setUp(self):
        self.base = current_dirname
        self.hiera = piera.Hiera(os.path.join(current_dirname, data_filename),
                                 version=5,
                                 name='test')

    def tearDown(self):
        os.chdir(self.base)


class TestPieraConfig(unittest.TestCase):
    def test_load_empty_config(self):
        obj = StringIO.StringIO("")

        with self.assertRaisesRegex(Exception, "Failed to parse base Hiera configuration"):
            piera.Hiera(obj)

    def test_invalid_backends_config(self):
        obj = StringIO.StringIO("""
            :backends:
                - nope
        """)

        with self.assertRaisesRegex(Exception, "Invalid Backend: `nope`"):
            piera.Hiera(obj)

    def test_invalid_hierarchy_config(self):
        obj = StringIO.StringIO("""
            :backends:
                - yaml
        """)

        with self.assertRaisesRegex(Exception, "Invalid Base Hiera Config: missing hierarchy key"):
            piera.Hiera(obj)

    def test_valid_config(self):
        obj = StringIO.StringIO("""
            :backends:
                - yaml
            :hierarchy:
                - common
            :yaml:
                :datadir: data
        """)

        piera.Hiera(obj)


class TestPiera(BaseTestPiera):
    def test_different_path(self):
        os.chdir(tempfile.gettempdir())
        hiera = piera.Hiera(os.path.join(self.base, data_filename), version=5, name='test')
        self.assertEqual(hiera.get('test_basic_get'), 'test_basic_get_works')
        self.assertEqual(hiera.get('test_hierarchy_get'), 'test_hierarchy_get_level1')

    def test_get(self):
        self.assertEqual(self.hiera.get('test_basic_get'), 'test_basic_get_works')
        self.assertEqual(self.hiera.get('test_hierarchy_get'), 'test_hierarchy_get_level1')
        self.assertEqual(self.hiera.get('test_hierarchy_get_2'), 'test_hierarchy_get_2_level2')
        self.assertEqual(self.hiera.get('test_basic_get', name=None), None)

    def test_get_functions(self):
        # Test Alias
        self.assertEqual(self.hiera.get('test_alias'), 'test_alias_works')
        with self.assertRaisesRegex(Exception, "Alias can not be used for string interpolation: `.*`"):
            self.hiera.get('test_alias_invalid', name='test')

        # Test Hiera
        obj = self.hiera.get('test_complex_alias')
        self.assertTrue(isinstance(obj, dict))
        self.assertEqual(obj['key1'], 'value1')

        # Test Literal
        self.assertEqual(self.hiera.get('test_literal'), 'hi')

        # Test Scope
        self.assertEqual(self.hiera.get('test_scope'), 'test')
        self.assertEqual(self.hiera.get('test_scope', name='wat'), 'wat')
        self.assertEqual(self.hiera.get('test_scope_ns', name='wat'), 'wat')

    def test_get_functions_deeply(self):
        self.assertEqual(self.hiera.get('test_resolve_hash', name='wat'), {
            'a': 'wat',
            'b': 1,
            'c': 'hi'
        })

        self.assertEqual(self.hiera.get('test_resolve_array', name='wat'), [
            'wat', 1, 'hi'
        ])

    def test_raw_context(self):
        self.assertEqual(self.hiera.get('test_scope_ns', context={'name': 'wat'}), 'wat')
        self.assertEqual(self.hiera.get('test_scope_ns', context={'name': 'wat'}, name='test'), 'test')

    def test_interpolate(self):
        self.assertEqual(self.hiera.get('test_interpolate'), 'this is interpolated: test')
        self.assertEqual(self.hiera.get('test_interpolate_ns'), 'this is interpolated: test')

    def test_falsey_values(self):
        self.assertEqual(self.hiera.get('test_empty_hash'), {})
        self.assertEqual(self.hiera.get('test_empty_list'), [])
        self.assertEqual(self.hiera.get('test_false_value'), False)
        self.assertEqual(self.hiera.get('test_null_value'), None)
        self.assertEqual(self.hiera.get('test_missing_value'), None)

    def test_default_value(self):
        self.assertEqual(self.hiera.get('nope', default=42), 42)
        self.assertEqual(self.hiera.get('test_literal', default=42), 'hi')

    def test_throw_keyerror(self):
        with self.assertRaises(KeyError):
            self.hiera.get('nope', throw=True)

    def test_has(self):
        self.assertTrue(self.hiera.has('test_complex_alias'))
        self.assertFalse(self.hiera.has('nope'))

    def test_rescope(self):
        hiera = self.hiera.scoped(name='wat')
        self.assertEqual(hiera.get('test_scope'), 'wat')
        self.assertEqual(hiera.get('test_scope_ns'), 'wat')
        self.assertEqual(hiera.get('test_scope_ns', name='test'), 'test')

        # Make sure we can still access the base hiera stuff
        self.assertEqual(hiera.base_file, self.hiera.base_file)

        with self.assertRaises(AttributeError):
            hiera.magical_nonexistant_thing()

    def test_override(self):
        self.assertEqual(self.hiera.get('test_override'), 'b')

    def test_merge(self):
        self.assertEqual(self.hiera.get('test_basic_merge', merge=list), ['a', 'b'])
        self.assertEqual(self.hiera.get('test_array_merge_a', merge=list), ['a', 'b', 'c'])
        self.assertEqual(self.hiera.get('test_array_merge_b', merge=list), ['a', 'b', 'c', 'd'])
        self.assertEqual(self.hiera.get('test_hash_merge_a', merge=dict), {'a': 1, 'b': 2})
        self.assertEqual(self.hiera.get('test_hash_merge_b', merge=dict), {'a': 1, 'b': 1})

    def test_interpolated_merge(self):
        self.assertEqual(self.hiera.get('test_interpolated_hash_merge', merge=dict), {'a': 'override-a-hi', 'b': 'default-b-hi'})

if __name__ == "__main__":
    base = os.getcwd()
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    unittest.main()
    os.chdir(base)
