from io import StringIO

from django.core.checks import Tags, run_checks
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class ProductionSafetyGuardTests(SimpleTestCase):
    def test_deploy_check_rejects_placeholder_secret_key(self):
        with override_settings(DEBUG=False, SECRET_KEY='replace-with-a-long-random-secret'):
            errors = run_checks(tags=[Tags.security], include_deployment_checks=True)
        self.assertIn('core.E001', {error.id for error in errors})

    def test_deploy_check_accepts_non_placeholder_secret_key(self):
        with override_settings(DEBUG=False, SECRET_KEY='prod-secret-key-with-enough-random-looking-length-123'):
            errors = run_checks(tags=[Tags.security], include_deployment_checks=True)
        self.assertNotIn('core.E001', {error.id for error in errors})

    def test_excel_workflow_audit_requires_confirmation_in_production(self):
        with override_settings(DEBUG=False, ALLOW_UNSAFE_MANAGEMENT_COMMANDS_IN_TESTS=False):
            with self.assertRaisesMessage(CommandError, 'Refusing to run excel_workflow_audit'):
                call_command('excel_workflow_audit', '--apply', '--wipe', stdout=StringIO())

    def test_excel_workflow_staged_requires_confirmation_in_production(self):
        with override_settings(DEBUG=False, ALLOW_UNSAFE_MANAGEMENT_COMMANDS_IN_TESTS=False):
            with self.assertRaisesMessage(CommandError, 'Refusing to run excel_workflow_staged'):
                call_command(
                    'excel_workflow_staged',
                    '--stage',
                    'baseline',
                    '--apply',
                    '--wipe',
                    stdout=StringIO(),
                )

    def test_reset_workflow_demo_requires_confirmation_in_production(self):
        with override_settings(DEBUG=False, ALLOW_UNSAFE_MANAGEMENT_COMMANDS_IN_TESTS=False):
            with self.assertRaisesMessage(CommandError, 'Refusing to run reset_workflow_demo'):
                call_command('reset_workflow_demo', stdout=StringIO())

    def test_bootstrap_demo_requires_confirmation_in_production(self):
        with override_settings(DEBUG=False, ALLOW_UNSAFE_MANAGEMENT_COMMANDS_IN_TESTS=False):
            with self.assertRaisesMessage(CommandError, 'Refusing to run bootstrap_demo'):
                call_command('bootstrap_demo', stdout=StringIO())

    def test_bootstrap_deploy_baseline_requires_confirmation_in_production(self):
        with override_settings(DEBUG=False, ALLOW_UNSAFE_MANAGEMENT_COMMANDS_IN_TESTS=False):
            with self.assertRaisesMessage(CommandError, 'Refusing to run bootstrap_deploy_baseline'):
                call_command('bootstrap_deploy_baseline', stdout=StringIO())
