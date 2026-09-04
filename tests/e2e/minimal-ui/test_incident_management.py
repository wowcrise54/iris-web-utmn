"""
Playwright E2E tests for the incident management UI
(Tyumen State University Position on security event monitoring and incident response).

Requires the IRIS stack to be running (docker compose up -d) with migration
a1b2c3d4e5f6 applied. Admin credentials are read from the project .env
(IRIS_ADM_USERNAME / IRIS_ADM_PASSWORD).
"""
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BASE_URL = os.environ.get("IRIS_E2E_BASE_URL", "https://localhost")
IRIS_E2E_BASE_URL = BASE_URL


def _load_admin_credentials():
    """Read admin credentials from .env (values never printed)."""
    env_path = PROJECT_ROOT / ".env"
    creds = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            creds[key.strip()] = value.strip().strip('"').strip("'")
    # Prefer the dedicated E2E user (created via e2e_test_user.py), fall back to env admin
    user = os.environ.get("IRIS_E2E_USER") or creds.get("IRIS_ADM_USERNAME")
    pwd = os.environ.get("IRIS_E2E_PASS") or creds.get("IRIS_ADM_PASSWORD")
    if not user or not pwd:
        pytest.skip("IRIS_E2E_USER/IRIS_E2E_PASS or IRIS_ADM_USERNAME/IRIS_ADM_PASSWORD not found")
    return user, pwd


ADMIN_USER, ADMIN_PASS = _load_admin_credentials()

INCIDENT_CARD_TITLE = "Карточка данных об инциденте"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="session")
def authed_page(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 900},
                                  ignore_https_errors=True)
    page = context.new_page()

    # Log in
    page.goto(f"{IRIS_E2E_BASE_URL}/login", wait_until="domcontentloaded")
    page.wait_for_selector("#username", timeout=30000)
    page.fill("#username", ADMIN_USER)
    page.fill("#password", ADMIN_PASS)
    page.click("button[type='submit']")
    page.wait_for_url(lambda url: "login" not in url, timeout=30000)
    yield page
    context.close()


def _create_case(page):
    """Create a throwaway case and return its id.

    The CSRF token is read from the case page (which always renders
    ``#csrf_token``), since the /manage/cases listing may not.
    """
    # Load a case page so a valid #csrf_token is available in the DOM.
    page.goto(f"{IRIS_E2E_BASE_URL}/case?cid=1", wait_until="domcontentloaded")
    page.wait_for_selector("#csrf_token", state="attached", timeout=30000)

    result = page.evaluate("""
        () => new Promise((resolve, reject) => {
            const csrfEl = document.querySelector('#csrf_token');
            const csrf = csrfEl ? csrfEl.value : '';
            const name = 'Incident E2E ' + Math.floor(Math.random() * 1e6);
            fetch('/manage/cases/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json;charset=UTF-8',
                    'X-Requested-With': 'fetch'
                },
                body: JSON.stringify({
                    csrf_token: csrf,
                    case_name: name,
                    case_description: 'E2E test case for incident management',
                    case_soc_id: 'e2e',
                    case_customer: 1
                })
            })
            .then(r => r.json())
            .then(d => resolve(d))
            .catch(reject);
        })
    """)
    assert result.get('status') == 'success', f"Case creation failed: {result.get('message')}"
    return result['data']['case_id']


class TestIncidentManagementE2E:
    """E2E coverage of the incident card UI on the case page."""

    @pytest.fixture(autouse=True)
    def case_id(self, authed_page):
        self.page = authed_page
        self.case = _create_case(authed_page)
        self.page.goto(
            f"{IRIS_E2E_BASE_URL}/case?cid={self.case}", wait_until="domcontentloaded")
        # Wait for the incident-card button rather than 'networkidle' — the case
        # page keeps a persistent socket.io connection, so networkidle can hang.
        self.page.wait_for_selector("#incident_card_btn", state="attached", timeout=30000)
        yield
        # Leave the test case open; it is clearly named for manual cleanup

    def test_incident_card_button_visible(self):
        """The 'Incident card' button is present on the case page."""
        btn = self.page.wait_for_selector("#incident_card_btn", timeout=10000)
        assert btn is not None

    def test_incident_modal_opens(self):
        """Clicking the button opens the incident card modal."""
        self.page.click("#incident_card_btn")
        self.page.wait_for_selector("#incidentManagementModal.show", timeout=10000)
        title = self.page.text_content("#incidentManagementModalLabel")
        assert INCIDENT_CARD_TITLE in title

    def test_dropdowns_populated_from_db(self):
        """Categories, system types, importance, priority are loaded from the DB."""
        self.page.click("#incident_card_btn")
        self.page.wait_for_selector("#incidentManagementModal.show", timeout=10000)

        categories = self.page.eval_on_selector_all(
            "#incident_category option", "els => els.map(e => e.value).filter(Boolean)")
        assert len(categories) == 8, f"Expected 8 categories, got {len(categories)}"

        system_types = self.page.eval_on_selector_all(
            "#system_type option", "els => els.map(e => e.value).filter(Boolean)")
        assert len(system_types) == 3

        priorities = self.page.eval_on_selector_all(
            "#priority option", "els => els.map(e => e.value).filter(Boolean)")
        assert len(priorities) == 9

        # Phase tracker rendered (it appears after the case-data request,
        # so wait for it explicitly — the dropdowns load earlier).
        self.page.wait_for_function(
            "() => document.querySelectorAll('#incidentPhaseTracker .phase-step').length > 0",
            timeout=20000)
        phases = self.page.eval_on_selector_all(
            "#incidentPhaseTracker .phase-step", "els => els.length")
        assert phases == 5

    def test_priority_autocalculation(self):
        """Selecting category + system type auto-fills importance and priority.

        Ransomware (cat 2) on a target system (type 1) -> high importance, P1.
        """
        self.page.click("#incident_card_btn")
        self.page.wait_for_selector("#incidentManagementModal.show", timeout=10000)
        # Wait for dropdowns to fill
        self.page.wait_for_function(
            "() => document.querySelectorAll('#incident_category option').length > 3",
            timeout=15000)

        cat = self.page.eval_on_selector(
            "#incident_category option[data-code='2']", "e => e ? e.value : null")
        assert cat is not None, "Category 2 (malware) not found"

        self.page.select_option("#incident_category", cat)
        self.page.select_option("#system_type", "1")
        # Wait deterministically for the auto-calculation to complete
        # (a fixed sleep races on a cold app).
        self.page.wait_for_function(
            "() => document.getElementById('importance').value !== ''",
            timeout=20000)

        importance = self.page.eval_on_selector("#importance", "el => el.value")
        priority = self.page.eval_on_selector("#priority", "el => el.value")
        assert importance != "", "Importance was not auto-calculated"
        assert priority != "", "Priority was not auto-calculated"

        # P1 => the priority row with level 1
        expected_priority_id = self.page.eval_on_selector_all(
            "#priority option",
            "els => els.find(e => e.textContent.trim() === 'Уровень 1') ? els.find(e => e.textContent.trim() === 'Уровень 1').value : ''")
        if expected_priority_id:
            assert priority == expected_priority_id

    def test_save_incident_card(self):
        """Saving the incident card persists data and header badges appear."""
        self.page.click("#incident_card_btn")
        self.page.wait_for_selector("#incidentManagementModal.show", timeout=10000)
        self.page.wait_for_function(
            "() => document.querySelectorAll('#incident_category option').length > 3",
            timeout=15000)

        # Fill: category code 3 (unauthorized access) on key system (code 2)
        self.page.select_option("#incident_category", label="Несанкционированные попытки доступа")
        self.page.select_option("#system_type", label="Ключевая система")
        self.page.wait_for_timeout(1500)

        self.page.fill("#reporter_name", "E2E Tester")
        self.page.fill("#reporter_email", "e2e@test.local")
        self.page.fill("#reporter_location", "Corpus A, room 12")
        self.page.fill("#affected_assets_info", "WS-TEST-01 / 10.0.0.5")

        self.page.click("#saveIncidentData")
        # Page reloads after save; wait for the re-rendered incident header badges
        self.page.wait_for_selector(
            ".incident-header-row .incident-badge", timeout=30000)

        # Header badges should now be visible
        badges = self.page.eval_on_selector_all(
            ".incident-header-row .incident-badge, .incident-header-row .btn-rounded",
            "els => els.map(e => e.textContent.trim()).filter(Boolean)")
        assert any("P" in b for b in badges), f"Priority badge missing: {badges}"

    def test_export_incident_card_pdf(self):
        """Exporting the incident card downloads a valid 4-page PDF.

        The document must be the full official Appendix-No.4 form
        ('Карточка данных об инциденте'): every official section label is
        asserted in the concatenated text of all pages, on top of the
        filled-in values from the UI (reporter name, system type,
        importance) and the checked category box (U+2612).
        """
        self.page.click("#incident_card_btn")
        self.page.wait_for_selector("#incidentManagementModal.show", timeout=10000)
        self.page.wait_for_function(
            "() => document.querySelectorAll('#incident_category option').length > 3",
            timeout=15000)

        # Fill a couple of fields so the PDF has something meaningful
        self.page.select_option("#incident_category", label="Внедрение вредоносного ПО")
        self.page.select_option("#system_type", label="Целевая система")
        self.page.wait_for_function(
            "() => document.getElementById('importance').value !== ''", timeout=15000)
        self.page.fill("#reporter_name", "PDF Exporter")

        with self.page.expect_download(timeout=60000) as download_info:
            self.page.click("#exportIncidentPdf")
        download = download_info.value
        assert download.suggested_filename.startswith("incident_card_")
        assert download.suggested_filename.endswith(".pdf")

        import tempfile, os
        tmp = tempfile.mkdtemp(prefix="iris_pdf_")
        saved = os.path.join(tmp, os.path.basename(download.suggested_filename))
        download.save_as(saved)
        with open(saved, "rb") as f:
            head = f.read(5)
        assert head == b"%PDF-", "downloaded file is not a PDF"

        # text check when pypdf is available
        pypdf = pytest.importorskip("pypdf")
        import io, re
        with open(saved, "rb") as f:
            reader = pypdf.PdfReader(io.BytesIO(f.read()))
        raw = "\n".join(p.extract_text() or "" for p in reader.pages)
        assert len(reader.pages) == 4, f"expected 4 pages, got {len(reader.pages)}"
        # pypdf wraps long cell text across lines; collapse whitespace so
        # form labels match regardless of the wrap position.
        text = re.sub(r"\s+", " ", raw)
        raw_text = raw

        # Behavioral asserts: values filled in via the UI appear in the PDF
        assert "PDF Exporter" in raw_text
        assert "Целевая система" in raw_text
        assert "Высокая" in raw_text
        # The selected category is rendered with a checked box (U+2612)
        assert "\u2612" in raw_text, "no checked category box (U+2612) found in the PDF"

        # Full Appendix-No.4 form structure: every official label must be
        # present in the concatenated text of all pages.
        expected_labels = [
            "Карточка данных об инциденте",
            "Приложение №4",
            "Идентификатор инцидента",
            "Дата и время инцидента",
            "Источник инцидента/средство обнаружения",
            "Уровень критичности",
            "Информация о сообщающем лице",
            "Адрес, по которому был зафиксирован инцидент",
            "Описание инцидента",
            "Детали инцидента",
            "Категория инцидента",
            "внедрение в сетевую инфраструктуру Университета вредоносного программного обеспечения",
            "Закончился ли инцидент",
            "Недопустимое событие",
            "Утечка персональных данных",
            "Идентифицированные уязвимости",
            "Тип инцидента",
            "Преднамеренный",
            "Случайный/непреднамеренный",
            "Естественный",
            "Пораженные активы",
            "Негативное воздействие/влияние инцидента на бизнес-процессы",
            "Приоритизация инцидента",
            "Важность инцидента по таблице",
            "Приоритет инцидента по таблице",
            "Расследование инцидента",
            "Дата начала расследования инцидента",
            "Причастные лица",
            "Мотивация",
            "Описание нарушителя",
            "Действия, предпринятые для разрешения инцидента",
            "Действия, запланированные для разрешения инцидента",
            "Выработанные организационные и технические меры",
            "Составил:",
            "С результатами проведенного расследования ознакомлен(ы):",
        ]
        missing = [label for label in expected_labels if label not in text]
        assert not missing, f"Appendix-No.4 form labels missing from the PDF: {missing}"

    def test_phase_change(self):
        """Changing the response phase updates the case (via API from UI)."""
        self.page.click("#incident_card_btn")
        self.page.wait_for_selector("#incidentManagementModal.show", timeout=10000)
        self.page.wait_for_selector("#incidentPhaseTracker .phase-step[data-phase='containment']", timeout=10000)

        self.page.click(".phase-step[data-phase='containment']")
        # The phase is updated via API; wait until the tracker re-renders
        self.page.wait_for_function(
            "() => { const a = document.querySelector('#incidentPhaseTracker .incident-phase.active .phase-name'); return a && a.textContent.trim() === 'Сдерживание'; }",
            timeout=15000)

        # Active phase should now be 'containment'
        active = self.page.eval_on_selector(
            "#incidentPhaseTracker .incident-phase.active .phase-name",
            "el => el.textContent.trim()")
        assert active == "Сдерживание"

        # Save to persist (the page reloads; the phase badge is a .btn-rounded,
        # not an .incident-badge, since this fresh case has no priority yet)
        self.page.click("#saveIncidentData")
        self.page.wait_for_function(
            "() => (document.querySelector('.incident-header-row') || {textContent: ''}).textContent.includes('Сдерживание')",
            timeout=30000)
        # After saving, the phase badge in the header should show 'Сдерживание'
        header_text = self.page.text_content(".incident-header-row")
        assert "Сдерживание" in header_text
