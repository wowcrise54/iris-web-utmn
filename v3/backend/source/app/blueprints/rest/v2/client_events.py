"""Authenticated browser diagnostics; technical events, not activity audit."""
import logging

from app.web import Blueprint, request
from app.blueprints.access_controls import ac_api_requires
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_error, response_api_success
from app.observability_logging import ClientEvents, logging_context

client_events_blueprint = Blueprint('client_events_rest_v2', __name__, url_prefix='/observability')
_intake = ClientEvents()
log = logging.getLogger('iris.browser')


@client_events_blueprint.post('/client-events')
@ac_api_requires()
def client_events():
    if request.content_length and request.content_length > 65536:
        return response_api_error('Event batch too large', status=413)
    if not request.is_json:
        return response_api_error('Expected JSON', status=415)
    try:
        events = _intake.validate(request.get_json(silent=True))
    except ValueError:
        return response_api_error('Invalid event batch', status=400)
    user_id = iris_current_user.id
    if not _intake.allow(user_id, len(events)):
        return response_api_error('Event rate limit exceeded', status=429)
    # Browser fields cannot override identity. No customer is inferred from an
    # arbitrary case/path: these are user events without a selected tenant.
    with logging_context(user_id=user_id, source='browser'):
        for event in events:
            fields = {key: value for key, value in event.items() if key not in ('level', 'message', 'stack')}
            fields['metadata'] = {'stack': event.get('stack', [])}
            log.log(getattr(logging, event['level']), event.get('message', event['event']), extra=fields)
    return response_api_success({'received': len(events)})
