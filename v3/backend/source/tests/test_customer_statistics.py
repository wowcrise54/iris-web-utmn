import datetime
from collections import namedtuple
import pytest

from app.business.customer_statistics import customer_cases_payload


CaseRow = namedtuple('CaseRow', 'case_id open_date close_date')


def test_customer_cases_payload_counts_periods_and_closed_case_average():
    cases = [
        CaseRow(1, datetime.date(2026, 10, 10), None),
        CaseRow(2, datetime.date(2026, 9, 20), datetime.date(2026, 9, 25)),
        CaseRow(3, datetime.date(2025, 6, 1), datetime.date(2025, 6, 4)),
    ]

    payload = customer_cases_payload(cases, today=datetime.date(2026, 10, 12))

    assert [case['case_id'] for case in payload['cases']] == [1, 2, 3]
    assert payload['stats'] == {
        'cases_last_month': 1,
        'cases_last_year': 1,
        'open_cases': 1,
        'last_year': 2025,
        'last_month': 9,
        'cases_rolling_week': 1,
        'cases_current_month': 1,
        'cases_current_year': 2,
        'ratio_year': 100.0,
        'ratio_month': 0.0,
        'average_case_duration': 4.0,
        'cases_total': 3,
    }


def test_customer_cases_payload_handles_empty_customer():
    payload = customer_cases_payload([], today=datetime.date(2026, 10, 12))

    assert payload['cases'] == []
    assert payload['stats']['cases_total'] == 0
    assert payload['stats']['average_case_duration'] == 0


def test_customer_cases_payload_averages_when_every_case_is_closed():
    cases = [
        CaseRow(1, datetime.date(2026, 10, 1), datetime.date(2026, 10, 3)),
        CaseRow(2, datetime.date(2026, 10, 1), datetime.date(2026, 10, 5)),
    ]
    stats = customer_cases_payload(cases, today=datetime.date(2026, 10, 12))['stats']
    assert stats['open_cases'] == 0
    assert stats['average_case_duration'] == 3


@pytest.mark.parametrize('today,previous_month,open_dates', [
    (datetime.date(2026, 1, 12), 12, [datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)]),
    (datetime.date(2026, 10, 31), 9, [datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)]),
])
def test_customer_cases_payload_counts_the_complete_previous_calendar_month(today, previous_month, open_dates):
    cases = [CaseRow(index, opened, None) for index, opened in enumerate(open_dates)]
    cases.append(CaseRow(3, today, None))
    stats = customer_cases_payload(cases, today=today)['stats']
    assert stats['last_month'] == previous_month
    assert stats['cases_last_month'] == 2
    assert stats['cases_current_month'] == 1
    assert stats['ratio_month'] == -50
