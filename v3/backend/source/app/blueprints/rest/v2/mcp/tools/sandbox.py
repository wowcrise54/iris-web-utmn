"""Read-only PT Sandbox task history for the current case."""
from app.blueprints.rest.v2.mcp.registry import mcp_tool
from app.business import ptsandbox as sandbox
from app.models.authorization import Permissions


@mcp_tool(name='iris_case_sandbox_list', description='List PT Sandbox checks for this case. Read only.',
          input_schema={'type': 'object', 'properties': {'before': {'type': 'integer', 'minimum': 1}},
                        'additionalProperties': False}, permissions=(Permissions.standard_user,), case_scoped=True, mvp=True)
def sandbox_list(args):
    return {'checks': sandbox.list_scans(args['case_identifier'], before=args.get('before'))}
