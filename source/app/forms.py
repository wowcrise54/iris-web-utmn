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

from app.web_forms import WebForm
from app.i18n import lazy_gettext
from wtforms import BooleanField
from wtforms import PasswordField
from wtforms import SelectField
from wtforms import SelectMultipleField
from wtforms import StringField
from wtforms import TextAreaField
from wtforms import widgets
from wtforms.fields.simple import SubmitField
from wtforms.validators import DataRequired
from wtforms.validators import Email
from wtforms.validators import InputRequired


class LoginForm(WebForm):
    username = StringField(lazy_gettext(u'Username'),
                           validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    password = PasswordField(lazy_gettext(u'Password'),
                             validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class MFASetupForm(WebForm):
    token = StringField(lazy_gettext('Token'),
                        validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    mfa_secret = StringField(lazy_gettext('MFA Secret'))
    user_password = PasswordField(lazy_gettext('Password'),
                                  validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    submit = SubmitField(lazy_gettext('Verify'))


class RegisterForm(WebForm):
    name = StringField(lazy_gettext(u'Name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    username = StringField(lazy_gettext(u'Username'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    password = PasswordField(lazy_gettext(u'Password'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    email = StringField(lazy_gettext(u'Email'), validators=[DataRequired(message=lazy_gettext('This field is required.')), Email(message=lazy_gettext('Invalid email address.'))])


class SearchForm(WebForm):
    search_type = StringField(lazy_gettext(u'Search Type'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    search_value = StringField(lazy_gettext(u'Search Value'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class AddCustomerForm(WebForm):
    customer_name = StringField(lazy_gettext(u'Customer name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    customer_description = TextAreaField(lazy_gettext(u'Customer description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    customer_sla = TextAreaField(lazy_gettext(u'Customer SLAs'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class AddAssetForm(WebForm):
    asset_name = StringField(lazy_gettext(u'Asset name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    asset_description = StringField(lazy_gettext(u'Asset description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    asset_icon_compromised = StringField(lazy_gettext(u'Asset icon compromised name'), default="ioc_question-mark.png")
    asset_icon_not_compromised = StringField(lazy_gettext(u'Asset icon not compromised name'), default="question-mark.png")


class AttributeForm(WebForm):
    attribute_content = TextAreaField(lazy_gettext(u'Attribute content'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class AddIocTypeForm(WebForm):
    type_name = StringField(lazy_gettext(u'Type name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    type_description = StringField(lazy_gettext(u'Type description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    type_taxonomy = TextAreaField(lazy_gettext(u'Type taxonomy'))
    type_validation_regex = StringField(lazy_gettext(u'Type validation regex'))
    type_validation_expect = StringField(lazy_gettext(u'Type validation expectation'))


class CaseClassificationForm(WebForm):
    name = StringField(lazy_gettext(u'Case classification name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    name_expanded = StringField(lazy_gettext(u'Case classification name expanded'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    description = StringField(lazy_gettext(u'Case classification description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class EvidenceTypeForm(WebForm):
    name = StringField(lazy_gettext(u'Evidence type name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    description = StringField(lazy_gettext(u'Evidence type description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class CaseStateForm(WebForm):
    state_name = StringField(lazy_gettext(u'Case state name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    state_description = StringField(lazy_gettext(u'Case state description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class AddReportTemplateForm(WebForm):
    report_name = StringField(lazy_gettext(u'Report name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    report_description = StringField(lazy_gettext(u'Report description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    report_name_format = StringField(lazy_gettext(u'Report name formating'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    report_language = SelectField(lazy_gettext(u'Language'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    report_type = SelectField(lazy_gettext(u'Report Type'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class CaseTemplateForm(WebForm):
    case_template_json = TextAreaField(lazy_gettext(u'Case Template JSON'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class AddUserForm(WebForm):
    user_login = StringField(lazy_gettext(u'Name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    user_name = StringField(lazy_gettext(u'Username'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    user_password = PasswordField(lazy_gettext(u'Password'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    user_email = StringField(lazy_gettext(u'Email'), validators=[DataRequired(message=lazy_gettext('This field is required.')), Email(message=lazy_gettext('Invalid email address.'))])
    user_is_service_account = BooleanField(lazy_gettext(u'Use as service account'))


class AddGroupForm(WebForm):
    group_name = StringField(lazy_gettext(u'Group name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    group_description = StringField(lazy_gettext(u'Group description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class AddOrganisationForm(WebForm):
    org_name = StringField(lazy_gettext(u'Organisation name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_description = StringField(lazy_gettext(u'Organisation description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_url = StringField(lazy_gettext(u'Organisation url'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_logo = StringField(lazy_gettext(u'Organisation logo'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_email = StringField(lazy_gettext(u'Organisation email'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_nationality = StringField(lazy_gettext(u'Organisation nationality'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_sector = StringField(lazy_gettext(u'Organisation nationality'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    org_type = StringField(lazy_gettext(u'Organisation type'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class ModalAddCaseAssetForm(WebForm):
    asset_id = SelectField(lazy_gettext(u'Asset type'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class AddCaseForm(WebForm):
    case_name = StringField(lazy_gettext(u'Case name'), validators=[InputRequired(message=lazy_gettext('This field is required.'))])
    case_description = StringField(lazy_gettext(u'Case description'), validators=[InputRequired(message=lazy_gettext('This field is required.'))])
    case_soc_id = StringField(lazy_gettext(u'SOC Ticket'))
    case_customer = SelectField(lazy_gettext(u'Customer'), validators=[InputRequired(message=lazy_gettext('This field is required.'))])
    case_organisations = SelectMultipleField(u'Organisations')
    classification_id = SelectField(lazy_gettext(u'Classification'))
    case_template_id = SelectField(lazy_gettext(u'Case Template'))


class ContactForm(WebForm):
    contact_name = StringField(lazy_gettext(u'Contact name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    contact_role = StringField(lazy_gettext(u'Contact role'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    contact_email = StringField(lazy_gettext(u'Contact email'), validators=[DataRequired(message=lazy_gettext('This field is required.')), Email(message=lazy_gettext('Invalid email address.'))])
    contact_work_phone = StringField(lazy_gettext(u'Work phone'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    contact_mobile_phone = StringField(lazy_gettext(u'Mobile phone'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    contact_note = TextAreaField(lazy_gettext(u'Contact description'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class PipelinesCaseForm(WebForm):
    pipeline = SelectField(lazy_gettext(u'Processing pipeline'))


class AssetBasicForm(WebForm):
    asset_name = StringField(lazy_gettext(u'Name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    asset_description = TextAreaField(lazy_gettext(u'Description'))
    asset_domain = StringField(lazy_gettext(u'Domain'))
    asset_ip = StringField(lazy_gettext(u'Domain'))
    asset_info = TextAreaField(lazy_gettext(u'Asset Info'))
    asset_compromise_status_id = SelectField(lazy_gettext(u'Compromise Status'))
    asset_type_id = SelectField(lazy_gettext(u'Asset Type'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    analysis_status_id = SelectField(lazy_gettext(u'Analysis Status'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    asset_tags = StringField(lazy_gettext(u'Asset Tags'))


class CaseEventForm(WebForm):
    event_title = StringField(lazy_gettext(u'Event Title'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    event_source = StringField(lazy_gettext(u'Event Source'))
    event_content = TextAreaField(lazy_gettext(u'Event Description'))
    event_raw = TextAreaField(lazy_gettext(u'Event Raw data'))
    event_assets = SelectField(lazy_gettext(u'Event Asset'))
    event_category_id = SelectField(lazy_gettext(u'Event Category'))
    event_tz = StringField(lazy_gettext(u'Event Timezone'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    event_in_summary = BooleanField(lazy_gettext(u'Add to summary'))
    event_tags = StringField(lazy_gettext(u'Event Tags'))
    event_in_graph = BooleanField(lazy_gettext(u'Display in graph'))


class CaseTaskForm(WebForm):
    task_title = StringField(lazy_gettext(u'Task Title'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    task_description = TextAreaField(lazy_gettext(u'Task description'))
    task_status_id = SelectField(lazy_gettext(u'Task status'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    task_assignees_id = SelectMultipleField(lazy_gettext(u'Assignee(s)'))
    task_tags = StringField(lazy_gettext(u'Task Tags'))


class CaseGlobalTaskForm(WebForm):
    task_title = StringField(lazy_gettext(u'Task Title'))
    task_description = TextAreaField(lazy_gettext(u'Task description'))
    task_assignee_id = SelectField(lazy_gettext(u'Task assignee'))
    task_status_id = SelectField(lazy_gettext(u'Task status'))
    task_tags = StringField(lazy_gettext(u'Task Tags'))


class ModalAddCaseIOCForm(WebForm):
    ioc_tags = StringField(lazy_gettext(u'IOC Tags'))
    ioc_value = TextAreaField(lazy_gettext(u'IOC Value'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    ioc_description = TextAreaField(lazy_gettext(u'IOC Description'))
    ioc_type_id = SelectField(lazy_gettext(u'IOC Type'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    ioc_tlp_id = SelectField(lazy_gettext(u'IOC TLP'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class ModalDSFileForm(WebForm):
    file_original_name = StringField(lazy_gettext(u'Filename'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    file_description = TextAreaField(lazy_gettext(u'file_description'))
    file_password = StringField(lazy_gettext(u'File password'))
    file_is_ioc = BooleanField(lazy_gettext(u'File is IOC'))
    file_is_evidence = BooleanField(lazy_gettext(u'File is Evidence'))


class CaseNoteForm(WebForm):
    note_title = StringField(lazy_gettext(u'Note title'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
    note_content = StringField(lazy_gettext(u'Note content'))


class AddModuleForm(WebForm):
    module_name = StringField(lazy_gettext(u'Module name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])


class UpdateModuleParameterForm(WebForm):
    module_name = StringField(lazy_gettext(u'Module name'), validators=[DataRequired(message=lazy_gettext('This field is required.'))])
