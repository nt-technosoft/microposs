"""Test package helpers.

`manage.py test apps.core.tests` can otherwise discover files from this
directory as top-level modules (`test_xxx`) and break relative imports.
"""

import importlib
import pkgutil
import unittest


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    package_name = __name__
    package_path = __path__
    for module_info in pkgutil.iter_modules(package_path):
        if not module_info.name.startswith('test_'):
            continue
        module = importlib.import_module(f'{package_name}.{module_info.name}')
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
