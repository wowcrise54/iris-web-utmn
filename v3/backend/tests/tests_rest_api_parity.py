from unittest import TestCase

from iris import Iris


class TestsRestApiParity(TestCase):

    def setUp(self) -> None:
        self._subject = Iris()

    def test_compromise_statuses_expose_enum_values(self):
        response = self._subject.get('/api/v2/manage/compromise-statuses')

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {'value': 0, 'name': 'To be determined'},
                {'value': 1, 'name': 'Compromised'},
                {'value': 2, 'name': 'Not compromised'},
                {'value': 3, 'name': 'Unknown'},
            ],
            response.json(),
        )

    def test_outcome_statuses_expose_enum_values(self):
        response = self._subject.get('/api/v2/manage/outcome-statuses')

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {'value': 0, 'name': 'Unknown'},
                {'value': 1, 'name': 'False positive'},
                {'value': 2, 'name': 'True positive with impact'},
                {'value': 3, 'name': 'Not applicable'},
                {'value': 4, 'name': 'True positive without impact'},
                {'value': 5, 'name': 'Legitimate'},
            ],
            response.json(),
        )
