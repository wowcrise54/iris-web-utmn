"""Start alert analysis without injecting its report into another chat."""
from app.blueprints.rest.v2.mcp.registry import mcp_tool
from app.blueprints.rest.v2.mcp.dispatch import MCPError
from app.blueprints.iris_user import iris_current_user
from app.business.alert_analysis import start_alert_job, get_alert_job, alert_metadata
from app.models.authorization import Permissions
from app.models.errors import BusinessProcessingError, ObjectNotFoundError


@mcp_tool(name='iris_alerts_analyze_start',
    description='Start full asynchronous alert analysis in a dedicated alert-scoped Yuki chat. Returns metadata and a link only; report stays in that chat. Do not busy-poll.',
    input_schema={'type': 'object', 'properties': {'alert_identifier': {'type': 'integer', 'minimum': 1}},
                  'required': ['alert_identifier'], 'additionalProperties': False},
    permissions=(Permissions.alerts_read,), mvp=True)
def start(args):
    try:
        return alert_metadata(start_alert_job(args['alert_identifier'], iris_current_user._get_current_object(), {}))
    except ObjectNotFoundError:
        raise MCPError(-32602, 'Alert not found') from None
    except BusinessProcessingError as exc:
        raise MCPError(-32602, exc.get_message()) from None


@mcp_tool(name='iris_alerts_analysis_get',
    description='Read caller alert analysis metadata, progress, coverage and dedicated chat link only. The report is available in that alert chat. Do not repeatedly poll queued/running jobs.',
    input_schema={'type': 'object', 'properties': {'alert_identifier': {'type': 'integer', 'minimum': 1},
                  'analysis_id': {'type': 'integer', 'minimum': 1}},
                  'required': ['alert_identifier', 'analysis_id'], 'additionalProperties': False},
    permissions=(Permissions.alerts_read,), mvp=True)
def get(args):
    try:
        return alert_metadata(get_alert_job(args['alert_identifier'], args['analysis_id'], iris_current_user.id))
    except ObjectNotFoundError:
        raise MCPError(-32602, 'Analysis not found') from None
