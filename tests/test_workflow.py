from pathlib import Path
import unittest
import yaml


class WorkflowTests(unittest.TestCase):
    def test_pages_publication_on_main_push_and_dispatch(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.load((root / '.github/workflows/daily.yml').read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']), {'push', 'workflow_dispatch'})
        self.assertEqual(workflow['on']['push']['branches'], ['main'])
        jobs = workflow['jobs']
        self.assertEqual(set(jobs), {'build', 'deploy'})
        self.assertEqual(jobs['build']['permissions'], {'contents': 'read'})
        self.assertEqual(jobs['deploy']['permissions'], {'pages': 'write', 'id-token': 'write'})
        self.assertEqual(jobs['deploy']['needs'], 'build')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')


if __name__ == '__main__':
    unittest.main()
