import unittest, os
import piera

try:
    import StringIO
except ImportError:
    import io as StringIO

class BaseTestPiera(unittest.TestCase):
    def setUp(self):
        self.base = os.getcwd()
        self.hiera = piera.Hiera('hiera.yaml', name='test')

    def tearDown(self):
        os.chdir(self.base)

class TestPieraConfig(unittest.TestCase):
    def test_load_empty_config(self):
        obj = StringIO.StringIO("")

        with self.assertRaisesRegexp(Exception, "Failed to parse base Hiera configuration"):
            h = piera.Hiera(obj)

    def test_invalid_backends_config(self):
        obj = StringIO.StringIO("""
            :backends:
                - nope
        """)

        with self.assertRaisesRegexp(Exception, "Invalid Backend: `nope`"):
            h = piera.Hiera(obj)

    def test_invalid_hierarchy_config(self):
        obj = StringIO.StringIO("""
            :backends:
                - yaml
        """)

        with self.assertRaisesRegexp(Exception, "Invalid Base Hiera Config: missing hierarchy key"):
            h = piera.Hiera(obj)

    def test_valid_config(self):
        obj  =StringIO.StringIO("""
            :backends:
                - yaml
            :hierarchy:
                - common
            :yaml:
                :datadir: data
        """)

        h = piera.Hiera(obj)

class TestPiera(BaseTestPiera):
    def test_different_path(self):
        os.chdir("/tmp")
        hiera = piera.Hiera(os.path.join(self.base, 'hiera.yaml'), name='test')
        self.assertEquals(hiera.get('test_basic_get'), 'test_basic_get_works')
        self.assertEquals(hiera.get('test_hierarchy_get'), 'test_hierarchy_get_level1')

    def test_get(self):
        self.assertEquals(self.hiera.get('test_basic_get'), 'test_basic_get_works')
        self.assertEquals(self.hiera.get('test_hierarchy_get'), 'test_hierarchy_get_level1')
        self.assertEquals(self.hiera.get('test_hierarchy_get_2'), 'test_hierarchy_get_2_level2')
        self.assertEquals(self.hiera.get('test_basic_get', name=None), None)

    def test_get_functions(self):
        # Test Alias
        self.assertEquals(self.hiera.get('test_alias'), 'test_alias_works')
        with self.assertRaisesRegexp(Exception, "Alias can not be used for string interpolation: `.*`"):
            self.hiera.get('test_alias_invalid', name='test')

        # Test Hiera
        obj = self.hiera.get('test_complex_alias')
        self.assertTrue(isinstance(obj, dict))
        self.assertEquals(obj['key1'], 'value1')
        
        # Test Literal
        self.assertEquals(self.hiera.get('test_literal'), 'hi')

        # Test Scope
        self.assertEquals(self.hiera.get('test_scope'), 'test')
        self.assertEquals(self.hiera.get('test_scope', name='wat'), 'wat')

    def test_interpolate(self):
        self.assertEquals(self.hiera.get('test_interpolate'), 'this is interpolated: test')

    def test_handles_empty_hash(self):
        self.assertEquals(self.hiera.get('test_empty_hash'), {})

if __name__ == "__main__":
    base = os.getcwd()
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    unittest.main()
    os.chdir(base)

