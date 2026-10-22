"""Keep only Appendix 4 data; restore deleted values from the pre-upgrade dump.

Operators must take and test an external pg_dump before applying this revision.
No backup table is left in the active database containing the removed fields.
"""

from alembic import op
import sqlalchemy as sa
import json

revision = "utmn_card_appendix4"
down_revision = "utmn_yuki_limits01"
branch_labels = None
depends_on = None

from copy import deepcopy

FIELDS = (
    "id",
    "incident_at",
    "detection_source",
    "criticality",
    "reporter_name",
    "reporter_phone",
    "reporter_email",
    "incident_location",
    "reporter_organization",
    "description",
    "affected_assets",
    "occurred_at",
    "detected_at",
    "notified_at",
    "categories",
    "completed",
    "unacceptable_event",
    "unacceptable_event_kinds",
    "vulnerabilities",
    "incident_types",
    "asset_data",
    "asset_hardware",
    "asset_software",
    "asset_communications",
    "asset_documentation",
    "business_impact",
    "prioritization_type",
    "priority_override",
    "investigation_started_at",
    "investigators",
    "incident_ended_at",
    "impact_ended_at",
    "investigation_ended_at",
    "report_url",
    "actors",
    "motives",
    "offender_description",
    "performed_actions",
    "planned_actions",
    "preventive_measures",
    "prepared_by",
    "prepared_position",
    "acquainted",
)


def clean_fields(fields):
    result = {}
    for key, entry in (fields or {}).items():
        if key not in FIELDS:
            continue
        value = deepcopy(entry.get("value"))
        if key == "investigators" and isinstance(value, list):
            # The form asks for names, not positions; preserve both existing values as text.
            value = "\n".join(
                " / ".join(str(p.get(k) or "") for k in ("name", "position")).strip(
                    " /"
                )
                for p in value
            )
        result[key] = dict(value=value, mode="manual", source=None, status="manual")
    location = (fields or {}).get("report_location", {}).get("value")
    if location:
        previous = result.get("report_url", {}).get("value")
        result["report_url"] = dict(
            value="\n".join(str(v) for v in (previous, location) if v),
            mode="manual",
            source=None,
            status="manual",
        )
    return result


def upgrade():
    bind = op.get_bind()
    for row in bind.execute(
        sa.text("SELECT case_id, fields FROM incident_cards FOR UPDATE")
    ).mappings():
        fields = clean_fields(row["fields"])
        bind.execute(
            sa.text(
                "UPDATE incident_cards SET fields=CAST(:fields AS jsonb), selections='{}'::jsonb, missing_sources='[]'::jsonb, revision=revision+1, updated_at=CURRENT_TIMESTAMP WHERE case_id=:case_id"
            ),
            {
                "fields": json.dumps(fields, ensure_ascii=False),
                "case_id": row["case_id"],
            },
        )


def downgrade():
    raise RuntimeError(
        "Appendix 4 cleanup is irreversible; restore the verified pre-upgrade dump"
    )
