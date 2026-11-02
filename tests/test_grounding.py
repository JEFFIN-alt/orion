"""Offline tests for deterministic numeric grounding; fixtures are not AI evaluations."""
import json
from unittest.mock import patch
import unittest

import test_synthesis as synthesis_tests
from orion.grounding import numbers, ungrounded_numbers
from orion.execution import ExecutionService
from orion.synthesis_verify import SynthesisVerifier


class GroundingUnitTests(unittest.TestCase):
    def test_wrong_fork_count_is_detected(self):
        allowed=['36,489 stars and 3,867 forks']
        self.assertEqual(ungrounded_numbers('36,489 stars and 38,672 forks',allowed),['38672'])
        self.assertEqual(ungrounded_numbers('36,489 stars and 3,867 forks',allowed),[])

    def test_numbers_in_source_ids_are_excluded(self):
        self.assertEqual(numbers('repository:866513204 doi:10.5040/9781350865778'),[])

    def test_decimals_are_checked_and_single_digits_ignored(self):
        self.assertEqual(ungrounded_numbers('4.5 and 7', ['4.0']), ['4.5'])
        self.assertEqual(ungrounded_numbers('7', []), [])


class GroundingVerifierTests(unittest.TestCase):
    setUp=synthesis_tests.SynthesisIntegrationTests.setUp
    approve=synthesis_tests.SynthesisIntegrationTests.approve

    def run_synthesis(self, mode):
        self.approve()
        with patch.dict('os.environ',{'ORION_SYNTHESIS_TEST_MODE':'wrong_number'}), patch('orion.synthesis_verify.NUMERIC_GROUNDING',mode):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        return run

    def test_warn_mode_passes_with_numeric_warning(self):
        run=self.run_synthesis('warn')
        self.assertEqual(run['latest_verification']['status'],'passed')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        numeric=next(c for c in record['checks'] if c['name']=='source_references')
        self.assertIn('executive_summary: 38672 not found in cited sources [repository:778431525]; interpretation needs review',numeric['warnings'])

    def test_fail_mode_rejects_wrong_numeric_claim(self):
        run=self.run_synthesis('fail')
        self.assertEqual(run['latest_verification']['status'],'failed')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        numeric=next(c for c in record['checks'] if c['name']=='numeric_grounding')
        self.assertFalse(numeric['passed'])

    def test_unknown_source_failure_does_not_suppress_grounding_advisory(self):
        self.approve()
        with patch.dict('os.environ',{'ORION_SYNTHESIS_TEST_MODE':'unknown_and_wrong_number'}):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['status'],'failed')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        self.assertEqual(record['status'],'failed')
        failed=next(c for c in record['checks'] if c['name']=='analysis_and_provenance')
        self.assertIn('unknown source ID',failed['reason'])
        references=next((c for c in record['checks'] if c['name']=='source_references'),{'warnings':[]})
        self.assertIn('key_findings.1: 38672 not found in cited sources [repository:778431525]; interpretation needs review',references['warnings'])

    def test_unknown_only_claim_is_reported_as_not_groundable(self):
        self.approve()
        with patch.dict('os.environ',{'ORION_SYNTHESIS_TEST_MODE':'unknown'}):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        references=next(c for c in record['checks'] if c['name']=='source_references')
        self.assertTrue(any('key_findings.0: not groundable: no resolvable source IDs'==warning for warning in references['warnings']))

    def test_advisory_exception_does_not_change_verification_outcome(self):
        self.approve()
        with patch('orion.synthesis_verify.ungrounded_numbers',side_effect=RuntimeError('fixture advisory failure')):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['status'],'succeeded')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        self.assertEqual(record['status'],'passed')
        references=next(c for c in record['checks'] if c['name']=='source_references')
        self.assertTrue(any(w=='advisory_error: RuntimeError: fixture advisory failure' for w in references['warnings']))

    def test_unparseable_analysis_records_skipped_advisory(self):
        self.approve()
        with patch.dict('os.environ',{'ORION_SYNTHESIS_TEST_MODE':'malformed'}):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['status'],'failed')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        references=next(c for c in record['checks'] if c['name']=='source_references')
        self.assertIn('advisory skipped: analysis unparseable',references['warnings'])

    def test_correct_fixture_has_no_numeric_warning(self):
        self.approve()
        run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['latest_verification']['status'],'passed')
        from orion.verification import VerificationService
        record=VerificationService(self.db).history(run['id'])[-1]
        numeric=next(c for c in record['checks'] if c['name']=='source_references')
        self.assertFalse(any('ungrounded number' in warning for warning in numeric['warnings']))
