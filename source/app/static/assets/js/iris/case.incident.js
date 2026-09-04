/**
 * Incident Management Module
 * Implements incident management functionality per Tyumen State University
 * Position on security event monitoring and incident response (Polozhenie).
 *
 * - Incident card fields (Appendix No. 4 of the Position)
 * - Automatic importance/priority calculation (Tables 5.1 / 5.2)
 * - Response phase tracking (registration -> containment -> eradication
 *   -> recovery -> closure, plus false-positive status)
 */

class IncidentManagement {
    constructor(caseId) {
        this.caseId = caseId;
        this.baseUrl = '/manage/incident';
        this.init();
    }

    async init() {
        this.userModified = new Set();
        await this.loadDropdownData();
        this.bindEvents();
        // Render the phase tracker immediately (default phase) so it is in
        // the DOM even if the case-data request is slow; loadCaseData()
        // re-renders it below with the persisted phase.
        this.renderPhaseTracker();
        await this.loadCaseData();
        this.renderPhaseTracker();
    }

    csrfPayload() {
        const token = (typeof $ !== 'undefined' && $('#csrf_token').length)
            ? $('#csrf_token').val()
            : null;
        return token || '';
    }

    async apiGet(url) {
        const response = await fetch(url, {
            headers: { 'X-Requested-With': 'fetch' }
        });
        return response.json();
    }

    async apiPost(url, payload) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json;charset=UTF-8',
                'X-Requested-With': 'fetch'
            },
            body: JSON.stringify(payload)
        });
        return response.json();
    }

    async loadDropdownData() {
        try {
            const [categories, systemTypes, importance, priorities,
                 incidentTypes, undesirableEvents, motivations, playbooks] = await Promise.all([
                this.apiGet(`${this.baseUrl}/categories/list`),
                this.apiGet(`${this.baseUrl}/system-types/list`),
                this.apiGet(`${this.baseUrl}/importance-levels/list`),
                this.apiGet(`${this.baseUrl}/priority-levels/list`),
                this.apiGet(`${this.baseUrl}/incident-types/list`),
                this.apiGet(`${this.baseUrl}/undesirable-events/list`),
                this.apiGet(`${this.baseUrl}/motivations/list`),
                this.apiGet(`${this.baseUrl}/playbooks/list`)
            ]);

            if (categories.status === 'success') this.populateSelect('incident_category', categories.data, true);
            if (systemTypes.status === 'success') this.populateSelect('system_type', systemTypes.data, true);
            if (importance.status === 'success') this.populateSelect('importance', importance.data, true);
            if (priorities.status === 'success') this.populateSelect('priority', priorities.data, true);
            if (incidentTypes.status === 'success') this.populateIncidentTypes(incidentTypes.data);
            if (undesirableEvents.status === 'success') this.populateSelect('undesirable_event', undesirableEvents.data, true);
            if (motivations.status === 'success') this.populateSelect('motivation', motivations.data, true);
            if (playbooks.status === 'success') this.populateSelect('playbook', playbooks.data, true);
        } catch (error) {
            console.error('Error loading incident management data:', error);
            if (typeof notify_error === 'function') notify_error('Failed to load incident management data');
        }
    }

    populateSelect(selectId, data, keepCodeAttribute) {
        const select = document.getElementById(selectId);
        if (!select) return;

        const emptyLabel = select.getAttribute('data-empty-label') || '— Выберите —';
        select.innerHTML = '';
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = emptyLabel;
        select.appendChild(empty);

        data.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = item.name || `Уровень ${item.level}`;
            if (keepCodeAttribute && item.code) option.setAttribute('data-code', item.code);
            select.appendChild(option);
        });
    }

    populateIncidentTypes(data) {
        const select = document.getElementById('incident_type');
        if (!select) return;

        select.innerHTML = '<option value="">— Выберите тип —</option>';

        const categoryOrder = ['преднамеренный', 'случайный', 'естественный', 'неизвестно'];
        const categoryLabels = {
            'преднамеренный': 'Преднамеренный',
            'случайный': 'Случайный / непреднамеренный',
            'естественный': 'Естественный',
            'неизвестно': 'Неизвестно'
        };

        categoryOrder.forEach(category => {
            if (data[category] && data[category].length) {
                const optgroup = document.createElement('optgroup');
                optgroup.label = categoryLabels[category] || category;
                data[category].forEach(type => {
                    const option = document.createElement('option');
                    option.value = type.id;
                    option.textContent = type.name;
                    optgroup.appendChild(option);
                });
                select.appendChild(optgroup);
            }
        });
    }

    bindEvents() {
        // Track user-modified fields so a delayed loadCaseData() response
        // cannot wipe fresh input (e.g. a just-triggered auto-calculation).
        const onCategoryChange = () => { this.userModified.add('incident_category'); this.calculatePriority(); };
        document.getElementById('incident_category').addEventListener('change', onCategoryChange);
        const onSystemTypeChange = () => { this.userModified.add('system_type'); this.calculatePriority(); };
        document.getElementById('system_type').addEventListener('change', onSystemTypeChange);

        ['incident_type', 'undesirable_event', 'motivation', 'playbook',
         'incident_occurrence_date', 'incident_discovery_date',
         'incident_report_date', 'investigation_start_date',
         'investigation_end_date', 'investigation_completion_date'
        ].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this.userModified.add(id));
        });

        // Text/textarea/date fields: mark on 'input' as well, so rapid
        // typing is protected before the delayed case-data response lands.
        ['importance', 'priority', 'response_phase',
         'reporter_name', 'reporter_phone', 'reporter_email',
         'reporter_location', 'reporter_organization', 'incident_duration',
         'affected_assets_info', 'business_impact_description',
         'vulnerability_info', 'perpetrator_description',
         'corrective_measures_org', 'corrective_measures_tech',
         'investigation_report_path', 'investigator_name',
         'resolution_actions_taken', 'resolution_actions_planned'
        ].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', () => this.userModified.add(id));
                el.addEventListener('change', () => this.userModified.add(id));
            }
        });

        document.getElementById('is_undesirable_event').addEventListener('change', (e) => {
            document.getElementById('undesirable_event').disabled = !e.target.checked;
            if (!e.target.checked) document.getElementById('undesirable_event').value = '';
        });

        document.getElementById('incident_duration').addEventListener('change', (e) => {
            const minutes = parseInt(e.target.value, 10) || 0;
            document.getElementById('incident_duration_seconds').value = minutes * 60;
        });

        document.getElementById('saveIncidentData').addEventListener('click', () => this.saveData());
        document.getElementById('exportIncidentPdf').addEventListener('click', () => this.exportPdf());

        // Phase tracker buttons
        document.querySelectorAll('#incidentPhaseTracker .phase-step[data-phase]').forEach(btn => {
            btn.addEventListener('click', () => this.setPhase(btn.getAttribute('data-phase')));
        });
    }

    renderPhaseTracker() {
        const tracker = document.getElementById('incidentPhaseTracker');
        if (!tracker) return;

        const phases = [
            { key: 'registration', name: 'Регистрация' },
            { key: 'containment', name: 'Сдерживание' },
            { key: 'eradication', name: 'Ликвидация' },
            { key: 'recovery', name: 'Восстановление' },
            { key: 'closure', name: 'Подведение итогов' }
        ];
        const current = (this.currentPhase || 'registration');
        const isFalsePositive = current === 'false_positive';

        let html = '<div class="incident-phases" role="list">';
        phases.forEach((phase, idx) => {
            const isCurrent = !isFalsePositive && current === phase.key;
            const isDone = !isFalsePositive && phases.findIndex(p => p.key === current) > idx;
            html += `<div class="incident-phase ${isCurrent ? 'active' : ''} ${isDone ? 'done' : ''}" role="listitem">
                        <button type="button" class="phase-step" data-phase="${phase.key}"
                                title="Перейти к этапу «${phase.name}»">
                            <span class="phase-index">${idx + 1}</span>
                            <span class="phase-name">${phase.name}</span>
                        </button>
                        ${idx < phases.length - 1 ? '<div class="phase-arrow"></div>' : ''}
                     </div>`;
        });
        if (isFalsePositive) {
            html += `<div class="incident-phase fp active"><button type="button" class="phase-step" data-phase="false_positive">
                        <span class="phase-index">!</span><span class="phase-name">Ложноположительный</span>
                     </button></div>`;
        }
        html += '</div>';
        tracker.innerHTML = html;

        // Rebind buttons (innerHTML replaced them)
        tracker.querySelectorAll('.phase-step[data-phase]').forEach(btn => {
            btn.addEventListener('click', () => this.setPhase(btn.getAttribute('data-phase')));
        });
    }

    async setPhase(phase) {
        try {
            const data = await this.apiPost(
                `${this.baseUrl}/case/${this.caseId}/phase?cid=${this.caseId}`,
                { csrf_token: this.csrfPayload(), response_phase: phase }
            );
            if (data.status === 'success') {
                this.currentPhase = phase;
                if (this.userModified) this.userModified.add('response_phase');
                const hidden = document.getElementById('response_phase');
                if (hidden) hidden.value = phase;
                this.renderPhaseTracker();
                if (typeof notify_success === 'function') notify_success('Этап реагирования обновлён');
            } else {
                if (typeof notify_error === 'function') notify_error(data.message || 'Не удалось обновить этап');
            }
        } catch (error) {
            console.error('Error updating phase:', error);
            if (typeof notify_error === 'function') notify_error('Ошибка обновления этапа реагирования');
        }
    }

    getSelectedCode(id) {
        const select = document.getElementById(id);
        if (!select) return null;
        const option = select.selectedOptions[0];
        return option ? (option.getAttribute('data-code') || null) : null;
    }

    async calculatePriority() {
        const categoryId = document.getElementById('incident_category').value;
        const systemTypeId = document.getElementById('system_type').value;

        const importanceSelect = document.getElementById('importance');
        const prioritySelect = document.getElementById('priority');
        importanceSelect.disabled = true;
        prioritySelect.disabled = true;

        if (!categoryId || !systemTypeId) {
            importanceSelect.value = '';
            prioritySelect.value = '';
            return;
        }

        try {
            const data = await this.apiPost(`${this.baseUrl}/calculate-priority`, {
                csrf_token: this.csrfPayload(),
                category_id: parseInt(categoryId, 10),
                system_type_id: parseInt(systemTypeId, 10)
            });

            if (data.status === 'success') {
                importanceSelect.value = data.data.importance_id || '';
                prioritySelect.value = data.data.priority_id || '';
                // Protect the computed values from a late loadCaseData()
                if (this.userModified) {
                    this.userModified.add('importance');
                    this.userModified.add('priority');
                }
                this.autoCalculated = true;
            }
        } catch (error) {
            console.error('Error calculating priority:', error);
            if (typeof notify_error === 'function') notify_error('Ошибка автоматического расчёта приоритета');
        }
    }

    toInputValue(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '';
        const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 16);
    }

    async loadCaseData() {
        try {
            const data = await this.apiGet(`${this.baseUrl}/case/${this.caseId}?cid=${this.caseId}`);
            if (data.status !== 'success') return;

            const c = data.data;

            this.setFieldValue('incident_category', c.incident_category_id);
            this.setFieldValue('system_type', c.system_type_id);
            this.setFieldValue('importance', c.importance_id);
            this.setFieldValue('priority', c.priority_id);
            this.setFieldValue('incident_type', c.incident_type_id);
            this.setFieldValue('undesirable_event', c.undesirable_event_id);
            this.setFieldValue('motivation', c.motivation_id);
            this.setFieldValue('playbook', c.playbook_id);
            this.setFieldValue('response_phase', c.response_phase);

            const fp = document.getElementById('is_undesirable_event');
            fp.checked = !!c.is_undesirable_event;
            document.getElementById('undesirable_event').disabled = !fp.checked;

            this.setDateTimeField('incident_occurrence_date', c.incident_occurrence_date);
            this.setDateTimeField('incident_discovery_date', c.incident_discovery_date);
            this.setDateTimeField('incident_report_date', c.incident_report_date);
            this.setDateTimeField('investigation_start_date', c.investigation_start_date);
            this.setDateTimeField('investigation_end_date', c.investigation_end_date);
            this.setDateTimeField('investigation_completion_date', c.investigation_completion_date);

            if (c.incident_duration_seconds) {
                document.getElementById('incident_duration').value = Math.round(c.incident_duration_seconds / 60);
            }

            this.setFieldValue('reporter_name', c.reporter_name);
            this.setFieldValue('reporter_phone', c.reporter_phone);
            this.setFieldValue('reporter_email', c.reporter_email);
            this.setFieldValue('reporter_location', c.reporter_location);
            this.setFieldValue('reporter_organization', c.reporter_organization);

            this.setFieldValue('affected_assets_info', c.affected_assets_info);
            this.setFieldValue('business_impact_description', c.business_impact_description);
            this.setFieldValue('vulnerability_info', c.vulnerability_info);
            this.setFieldValue('perpetrator_description', c.perpetrator_description);
            this.setFieldValue('corrective_measures_org', c.corrective_measures_org);
            this.setFieldValue('corrective_measures_tech', c.corrective_measures_tech);
            this.setFieldValue('investigation_report_path', c.investigation_report_path);
            this.setFieldValue('investigator_name', c.investigator_name);
            this.setFieldValue('resolution_actions_taken', c.resolution_actions_taken);
            this.setFieldValue('resolution_actions_planned', c.resolution_actions_planned);

            this.currentPhase = c.response_phase || 'registration';
            this.renderPhaseTracker();
        } catch (error) {
            console.error('Error loading case incident data:', error);
        }
    }

    setFieldValue(id, value) {
        // Do not clobber a field the user already changed — a slow
        // loadCaseData() response must not wipe fresh user input.
        if (this.userModified && this.userModified.has(id)) return;
        const element = document.getElementById(id);
        if (element) element.value = value || '';
    }

    setDateTimeField(id, dateTimeString) {
        const element = document.getElementById(id);
        if (element) element.value = this.toInputValue(dateTimeString);
    }

    collectFormData() {
        const val = (id) => {
            const el = document.getElementById(id);
            return el ? el.value : '';
        };
        const intVal = (id) => {
            const v = val(id);
            return v ? parseInt(v, 10) : null;
        };

        return {
            csrf_token: this.csrfPayload(),

            incident_category_id: intVal('incident_category'),
            system_type_id: intVal('system_type'),
            importance_id: intVal('importance'),
            priority_id: intVal('priority'),
            incident_type_id: intVal('incident_type'),
            undesirable_event_id: intVal('undesirable_event'),
            motivation_id: intVal('motivation'),
            playbook_id: intVal('playbook'),
            is_undesirable_event: document.getElementById('is_undesirable_event').checked,

            incident_occurrence_date: val('incident_occurrence_date') || null,
            incident_discovery_date: val('incident_discovery_date') || null,
            incident_report_date: val('incident_report_date') || null,
            incident_duration_seconds: intVal('incident_duration_seconds'),

            investigation_start_date: val('investigation_start_date') || null,
            investigation_end_date: val('investigation_end_date') || null,
            investigation_completion_date: val('investigation_completion_date') || null,
            impact_end_date: null,
            response_phase: val('response_phase') || this.currentPhase || 'registration',

            reporter_name: val('reporter_name'),
            reporter_phone: val('reporter_phone'),
            reporter_email: val('reporter_email'),
            reporter_location: val('reporter_location'),
            reporter_organization: val('reporter_organization'),

            affected_assets_info: val('affected_assets_info'),
            business_impact_description: val('business_impact_description'),
            vulnerability_info: val('vulnerability_info'),
            perpetrator_description: val('perpetrator_description'),
            corrective_measures_org: val('corrective_measures_org'),
            corrective_measures_tech: val('corrective_measures_tech'),
            investigation_report_path: val('investigation_report_path'),
            investigator_name: val('investigator_name'),
            resolution_actions_taken: val('resolution_actions_taken'),
            resolution_actions_planned: val('resolution_actions_planned')
        };
    }

    async saveData(reloadPage = true) {
        const saveBtn = document.getElementById('saveIncidentData');
        const originalHtml = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Сохранение…';

        try {
            const formData = this.collectFormData();
            if (!formData.response_phase) formData.response_phase = this.currentPhase || 'registration';
            const data = await this.apiPost(`${this.baseUrl}/case/${this.caseId}/update?cid=${this.caseId}`, formData);

            if (data.status === 'success') {
                if (typeof notify_success === 'function') notify_success('Данные инцидента сохранены');
                if (reloadPage) {
                    // Reload the page so header badges and summary reflect the new data
                    setTimeout(() => location.reload(), 400);
                }
            } else {
                if (typeof notify_error === 'function') notify_error(data.message || 'Ошибка при сохранении');
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalHtml;
            }
        } catch (error) {
            console.error('Error saving incident data:', error);
            if (typeof notify_error === 'function') notify_error('Ошибка при сохранении данных инцидента');
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalHtml;
        }
    }

    async exportPdf() {
        const btn = document.getElementById('exportIncidentPdf');
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Подготовка…';

        try {
            // Persist the current form values quietly (no page reload), so
            // the PDF reflects the filled-in card and the download survives.
            const formData = this.collectFormData();
            if (!formData.response_phase) formData.response_phase = this.currentPhase || 'registration';
            const data = await this.apiPost(
                `${this.baseUrl}/case/${this.caseId}/update?cid=${this.caseId}`, formData);
            if (data.status !== 'success') {
                if (typeof notify_error === 'function') notify_error(data.message || 'Не удалось сохранить данные перед экспортом');
                return;
            }
            // Trigger the browser download of the rendered PDF via an
            // anchor in the current page (reliable for popup blockers and
            // browser automation alike).
            const url = `${this.baseUrl}/case/${this.caseId}/export-pdf?cid=${this.caseId}`;
            const a = document.createElement('a');
            a.href = url;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            a.remove();
            if (typeof notify_success === 'function') notify_success('Файл PDF формируется');
        } catch (error) {
            console.error('Error exporting incident PDF:', error);
            if (typeof notify_error === 'function') notify_error('Ошибка экспорта в PDF');
        } finally {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}

// Initialize on page load. The modal markup is always present in the DOM and
// belongs to the current case (get_caseid()), so we do NOT rely on the
// Bootstrap 'show.bs.modal' event — Bootstrap 4 dispatches it through jQuery,
// so a native addEventListener('show.bs.modal') never fires.
document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('incidentManagementModal');
    if (!modal) return;

    const caseId = (typeof get_caseid === 'function') ? get_caseid() : null;
    if (caseId) {
        window.incidentManagement = new IncidentManagement(parseInt(caseId, 10));
    }
});
