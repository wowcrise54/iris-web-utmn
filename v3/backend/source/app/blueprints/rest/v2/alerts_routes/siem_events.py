from app.web import Blueprint, request, session
from app.blueprints.access_controls import ac_api_requires, ac_current_user_has_customer_access
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_success, response_api_error, response_api_not_found
from app.business.alerts import alerts_get
from app.business.maxpatrol_ingestion import list_alert_events
from app.models.authorization import Permissions
from app.models.errors import BusinessProcessingError, ObjectNotFoundError


alerts_siem_events_blueprint = Blueprint(
    'alerts_siem_events', __name__, url_prefix='/<int:identifier>/siem-events')


@alerts_siem_events_blueprint.get('')
@ac_api_requires(Permissions.alerts_read)
def get_siem_events(identifier):
    try:
        alert = alerts_get(
            iris_current_user, session.get('permissions') or 0, identifier,
            fallback_customer_access=ac_current_user_has_customer_access)
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 25))
        if offset < 0 or limit < 1:
            raise ValueError('Invalid event pagination')
        return response_api_success(list_alert_events(alert, offset=offset, limit=min(limit, 25)))
    except ObjectNotFoundError:
        return response_api_not_found()
    except BusinessProcessingError as exc:
        return response_api_error(exc.get_message(), data=exc.get_data())
    except (ValueError, TypeError):
        return response_api_error('Invalid event pagination')
