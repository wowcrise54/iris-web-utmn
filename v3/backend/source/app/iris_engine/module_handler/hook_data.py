"""Reload queued ORM identities; merging old snapshots can revert analyst edits."""
from sqlalchemy import inspect


def reload_hook_data(data, session):
    result = []
    for item in data if isinstance(data, list) else [data]:
        state = inspect(item, raiseerr=False)
        if state is not None and getattr(state, 'identity', None) is not None:
            current = session.get(type(item), state.identity, populate_existing=True)
            if current is not None:
                result.append(current)
        else:
            result.append(item)
    return result
