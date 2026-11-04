"""Lifecycle metadata must expose no prompt, tool arguments or results."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('chat_progress', Path(__file__).resolve().parents[1] / 'source/app/blueprints/rest/v2/case_chat/progress.py')
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


class ChatProgressTests(unittest.TestCase):
    def test_tool_start_and_approval(self):
        for pending, stage in [(False, 'executing_tool'), (True, 'awaiting_approval')]:
            self.assertEqual(progress.progress_for_event('assistant_tool_start', {
                'tool_name': 'test', 'tool_use_id': 'a', 'pending': pending,
                'arguments': {'private': 'secret'},
            }), {'stage': stage, 'tool_name': 'test', 'tool_use_id': 'a'})

    def test_results_completion_and_errors_are_metadata_only(self):
        for event, stage in [('assistant_tool_result', 'processing_result'), ('assistant_end', 'completed'), ('error', 'failed')]:
            self.assertEqual(progress.progress_for_event(event, {'result': 'private', 'message': 'private'}), {'stage': stage})
        self.assertIsNone(progress.progress_for_event('assistant_progress', {'stage': 'waiting_model'}))

if __name__ == '__main__':
    unittest.main()
