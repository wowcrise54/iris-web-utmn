#  IRIS Source Code
#  Copyright (C) 2021 - Airbus CyberSecurity (SAS)
#  ir@cyberactionlab.net
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Incident management routes (per Tyumen State University Position on
security event monitoring and incident response).

Implements the prioritization rules of Table 5.1 (importance) and
Table 5.2 (priority) of the Position, plus the incident card fields
of Appendix No. 4.
"""
from flask import Blueprint
from flask import request
from flask import Response
from flask_login import current_user

from app import app
from app import db
from app.models.models import IncidentCategory, SystemType, IncidentImportance, IncidentPriority
from app.models.models import IncidentType, UndesirableEvent, ProtagonistMotivation, Playbook
from app.models import CaseStatus
from app.models.cases import Cases
from app.schema.marshables import CaseDetailsSchema
from app.blueprints.incident_management.incident_pdf import (
    build_incident_card_pdf, incident_card_filename,
)
from app.models.authorization import CaseAccessLevel
from app.iris_engine.utils.tracker import track_activity
from app.util import response_error, response_success, ac_api_case_requires, ac_api_requires, ac_case_requires
from app.blueprints.incident_management.prioritization import (
    calc_importance as _calc_importance,
    calc_priority as _calc_priority,
)

incident_management_blueprint = Blueprint('incident_management',
                                          __name__,
                                          url_prefix='/manage/incident')

log = app.logger

# Response phases of the Position (5 stages) + false positive status
RESPONSE_PHASES = ['registration', 'containment', 'eradication', 'recovery', 'closure', 'false_positive']

RESPONSE_PHASE_NAMES = {
    'registration': 'Регистрация',
    'containment': 'Сдерживание',
    'eradication': 'Ликвидация',
    'recovery': 'Восстановление',
    'closure': 'Подведение итогов',
    'false_positive': 'Ложноположительный',
}


def _parse_datetime(value):
    """Parse a datetime string into a datetime object (None if empty)."""
    if not value:
        return None
    from datetime import datetime
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _dump_datetime(value):
    return value.isoformat() if value else None


def _priority_from_row(system_type_code, importance_row):
    """Resolve (importance id, priority) for a (system type, importance level) row.

    References are resolved from the database so that PKs never depend on
    seed ordering.
    """
    importance = IncidentImportance.query.filter_by(code=int(importance_row)).first()
    if not importance:
        return None, None
    priority_level = _calc_priority(system_type_code, importance_row)
    priority = IncidentPriority.query.filter_by(level=priority_level).first() if priority_level else None
    return (importance.id if importance else None), (priority.id if priority else None)


@incident_management_blueprint.route('/categories/list', methods=['GET'])
@ac_api_requires()
def list_incident_categories():
    """List all incident categories."""
    categories = IncidentCategory.query.order_by(IncidentCategory.code).all()
    return response_success("", data=[{
        'id': c.id,
        'code': c.code,
        'name': c.name,
        'description': c.description
    } for c in categories])


@incident_management_blueprint.route('/system-types/list', methods=['GET'])
@ac_api_requires()
def list_system_types():
    """List all system types."""
    types = SystemType.query.order_by(SystemType.code).all()
    return response_success("", data=[{
        'id': t.id,
        'code': t.code,
        'name': t.name,
        'description': t.description
    } for t in types])


@incident_management_blueprint.route('/importance-levels/list', methods=['GET'])
@ac_api_requires()
def list_importance_levels():
    """List all importance levels."""
    levels = IncidentImportance.query.order_by(IncidentImportance.code).all()
    return response_success("", data=[{
        'id': l.id,
        'code': l.code,
        'name': l.name
    } for l in levels])


@incident_management_blueprint.route('/priority-levels/list', methods=['GET'])
@ac_api_requires()
def list_priority_levels():
    """List all priority levels (1-9)."""
    priorities = IncidentPriority.query.order_by(IncidentPriority.level).all()
    return response_success("", data=[{
        'id': p.id,
        'level': p.level
    } for p in priorities])


@incident_management_blueprint.route('/incident-types/list', methods=['GET'])
@ac_api_requires()
def list_incident_types():
    """List all incident types grouped by category."""
    types = IncidentType.query.order_by(IncidentType.category, IncidentType.code).all()
    result = {}
    for t in types:
        if t.category not in result:
            result[t.category] = []
        result[t.category].append({
            'id': t.id,
            'code': t.code,
            'name': t.name
        })
    return response_success("", data=result)


@incident_management_blueprint.route('/undesirable-events/list', methods=['GET'])
@ac_api_requires()
def list_undesirable_events():
    """List all undesirable events."""
    events = UndesirableEvent.query.order_by(UndesirableEvent.id).all()
    return response_success("", data=[{
        'id': e.id,
        'name': e.name,
        'description': e.description
    } for e in events])


@incident_management_blueprint.route('/motivations/list', methods=['GET'])
@ac_api_requires()
def list_motivations():
    """List all protagonist motivations."""
    motivations = ProtagonistMotivation.query.order_by(ProtagonistMotivation.code).all()
    return response_success("", data=[{
        'id': m.id,
        'code': m.code,
        'name': m.name
    } for m in motivations])


@incident_management_blueprint.route('/playbooks/list', methods=['GET'])
@ac_api_requires()
def list_playbooks():
    """List all active playbooks."""
    playbooks = Playbook.query.filter_by(is_active=True).order_by(Playbook.name).all()
    return response_success("", data=[{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'category_id': p.category_id
    } for p in playbooks])


@incident_management_blueprint.route('/case/<int:caseid>', methods=['GET'])
@ac_api_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def get_case_incident_data(caseid):
    """Get incident management data for a case."""
    case = Cases.query.filter(Cases.case_id == caseid).first()
    if not case:
        return response_error("Case not found")

    return response_success("", data=CaseDetailsSchema().dump(case))


@incident_management_blueprint.route('/case/<int:caseid>/update', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def update_case_incident_data(caseid):
    """Update incident management fields for a case (Appendix No. 4 card)."""
    case = Cases.query.filter(Cases.case_id == caseid).first()
    if not case:
        return response_error("Case not found")

    data = request.get_json()
    if not data:
        return response_error("Empty JSON body")

    def set_field(name, value):
        if name in data:
            setattr(case, name, value)

    # Classification fields
    set_field('incident_category_id', data.get('incident_category_id') or None)
    set_field('system_type_id', data.get('system_type_id') or None)
    set_field('incident_type_id', data.get('incident_type_id') or None)
    set_field('undesirable_event_id', data.get('undesirable_event_id') or None)
    set_field('is_undesirable_event', bool(data.get('is_undesirable_event')))

    # Importance / priority are resolved by code (see calculate-priority endpoint);
    # accept ids directly as well for forward compatibility.
    importance_id = data.get('importance_id')
    priority_id = data.get('priority_id')
    if importance_id:
        importance = IncidentImportance.query.get(int(importance_id))
        set_field('importance_id', importance.id if importance else None)
    if priority_id:
        priority = IncidentPriority.query.get(int(priority_id))
        set_field('priority_id', priority.id if priority else None)

    # Response phase
    if 'response_phase' in data and data['response_phase']:
        if data['response_phase'] not in RESPONSE_PHASES:
            return response_error(f"Invalid response phase: {data['response_phase']}")
        set_field('response_phase', data['response_phase'])

    # Investigation dates (Appendix No. 4)
    for field in ('investigation_start_date', 'investigation_end_date', 'impact_end_date',
                  'investigation_completion_date'):
        if field in data:
            setattr(case, field, _parse_datetime(data[field]))

    # Reporter info
    for field in ('reporter_name', 'reporter_phone', 'reporter_email',
                  'reporter_location', 'reporter_organization'):
        set_field(field, data.get(field) or None)

    # Incident timing
    for field in ('incident_occurrence_date', 'incident_discovery_date', 'incident_report_date'):
        if field in data:
            setattr(case, field, _parse_datetime(data[field]))
    if 'incident_duration_seconds' in data:
        duration = data['incident_duration_seconds']
        if duration is None or duration == '':
            set_field('incident_duration_seconds', None)
        else:
            try:
                set_field('incident_duration_seconds', int(duration))
            except (TypeError, ValueError):
                return response_error("incident_duration_seconds must be an integer")

    # Playbook
    playbook_id = data.get('playbook_id')
    set_field('playbook_id', playbook_id or None)

    # Additional fields
    for field in ('affected_assets_info', 'business_impact_description', 'vulnerability_info',
                  'perpetrator_description', 'corrective_measures_org', 'corrective_measures_tech',
                  'investigation_report_path', 'investigator_name',
                  'resolution_actions_taken', 'resolution_actions_planned'):
        set_field(field, data.get(field) or None)
    set_field('motivation_id', data.get('motivation_id') or None)

    db.session.commit()
    track_activity("updated incident data", caseid)

    return response_success("Incident data updated")


@incident_management_blueprint.route('/case/<int:caseid>/phase', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def update_case_response_phase(caseid):
    """Update the current response phase of a case."""
    case = Cases.query.filter(Cases.case_id == caseid).first()
    if not case:
        return response_error("Case not found")

    data = request.get_json() or {}
    phase = data.get('response_phase')
    if phase not in RESPONSE_PHASES:
        return response_error(f"Invalid response phase: {phase}")

    case.response_phase = phase
    db.session.commit()
    track_activity(f"incident response phase -> {RESPONSE_PHASE_NAMES[phase]}", caseid)

    return response_success("Phase updated")


@incident_management_blueprint.route('/case/<int:caseid>/export-pdf')
@ac_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def export_case_incident_pdf(caseid, url_redir):
    """Export the incident card of a case as a downloadable PDF file.

    A browser download (GET). Requires read access to the case.
    """
    case = Cases.query.filter(Cases.case_id == caseid).first()
    if not case:
        return response_error("Case not found")

    # Mirror the status_name logic used on the case page for the PDF header.
    try:
        case.status_name = CaseStatus(case.status_id).name.replace('_', ' ').title()
    except (ValueError, KeyError):
        case.status_name = ''

    generated_by = (current_user.user or current_user.name) if current_user else None
    try:
        pdf_bytes = build_incident_card_pdf(case, generated_by=generated_by)
    except Exception:
        log.exception("Failed to build incident card PDF for case %s", caseid)
        return response_error("Failed to generate the incident card PDF"), 500

    filename = incident_card_filename(case)
    track_activity("exported incident card to PDF", caseid)
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@incident_management_blueprint.route('/calculate-priority', methods=['POST'])
@ac_api_requires()
def calculate_priority():
    """Calculate incident importance and priority per Tables 5.1 and 5.2.

    Accepts either database ids (category_id/system_type_id) or codes
    (category_code/system_type_code). Returns importance and priority
    as ids and codes.
    """
    data = request.get_json()
    if not data:
        return response_error("Empty JSON body")

    category_code = data.get('category_code')
    system_type_code = data.get('system_type_code')

    if not category_code:
        category_id = data.get('category_id')
        if not category_id:
            return response_error("Missing category_id or category_code")
        category = IncidentCategory.query.get(int(category_id))
        if not category:
            return response_error("Unknown incident category")
        category_code = category.code

    if not system_type_code:
        system_type_id = data.get('system_type_id')
        if not system_type_id:
            return response_error("Missing system_type_id or system_type_code")
        system_type = SystemType.query.get(int(system_type_id))
        if not system_type:
            return response_error("Unknown system type")
        system_type_code = system_type.code

    try:
        importance_row = _calc_importance(category_code, system_type_code)
    except (KeyError, TypeError, ValueError):
        return response_error("Invalid category or system type")
    if not importance_row:
        return response_error("Cannot calculate importance")

    importance_id, priority_id = _priority_from_row(system_type_code, importance_row)
    priority_level = _calc_priority(system_type_code, importance_row)

    return response_success("", data={
        'importance_id': importance_id,
        'importance_code': importance_row,
        'priority': priority_level,
        'priority_id': priority_id,
    })
