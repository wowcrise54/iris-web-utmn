"""Public lifecycle metadata derived from observable chat events."""


def progress_for_event(name: str, payload: dict) -> dict | None:
    if name == 'assistant_tool_start':
        return {
            'stage': 'awaiting_approval' if payload.get('pending') else 'executing_tool',
            'tool_name': payload['tool_name'],
            'tool_use_id': payload['tool_use_id'],
        }
    stage = {
        'assistant_tool_result': 'processing_result',
        'assistant_end': 'completed',
        'error': 'failed',
    }.get(name)
    return {'stage': stage} if stage else None
