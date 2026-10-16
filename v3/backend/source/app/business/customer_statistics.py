import datetime


def customer_cases_payload(cases, today=None):
    today = today or datetime.date.today()
    this_month_start = today.replace(day=1)
    last_month_start = (this_month_start - datetime.timedelta(days=1)).replace(day=1)
    case_rows = [case._asdict() for case in cases]
    stats = {
        'cases_last_month': 0,
        'cases_last_year': 0,
        'open_cases': 0,
        'last_year': today.year - 1,
        'last_month': last_month_start.month,
        'cases_rolling_week': 0,
        'cases_current_month': 0,
        'cases_current_year': 0,
        'ratio_year': 0,
        'ratio_month': 0,
        'average_case_duration': 0,
        'cases_total': len(cases),
    }
    last_year_start = datetime.date(today.year - 1, 1, 1)
    last_year_end = datetime.date(today.year - 1, 12, 31)
    this_year_start = datetime.date(today.year, 1, 1)
    closed_durations = []

    for case in cases:
        if case.open_date is not None:
            if today - datetime.timedelta(days=7) <= case.open_date <= today:
                stats['cases_rolling_week'] += 1
            if this_month_start <= case.open_date <= today:
                stats['cases_current_month'] += 1
            if this_year_start <= case.open_date <= today:
                stats['cases_current_year'] += 1
            if last_month_start <= case.open_date < this_month_start:
                stats['cases_last_month'] += 1
            if last_year_start <= case.open_date <= last_year_end:
                stats['cases_last_year'] += 1
        if case.close_date is None:
            stats['open_cases'] += 1
        elif case.open_date is not None:
            closed_durations.append((case.close_date - case.open_date).days)

    def change(current, previous):
        return ((current - previous) / previous) * 100 if previous else current * 100

    stats['ratio_year'] = change(stats['cases_current_year'], stats['cases_last_year'])
    stats['ratio_month'] = change(stats['cases_current_month'], stats['cases_last_month'])
    if closed_durations:
        stats['average_case_duration'] = sum(closed_durations) / len(closed_durations)
    return {'cases': case_rows, 'stats': stats}
