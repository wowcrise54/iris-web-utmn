#  IRIS Source Code
#  Copyright (C) 2026 - DFIR-IRIS
#  contact@dfir-iris.org
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

"""Persistence of the investigation graph of a case.

The `*_rows` readers return plain dicts (one query per kind, no per-row
query), so the assembly in `app.business.case_graph_assembly` stays a
pure function over plain data.
"""

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.db import db
from app.models.case_graph import CaseGraphEdge, CaseGraphRelationType

def case_graph_db_add(obj):
    """Stage the relation; the commit reports uniqueness conflicts."""
    db.session.add(obj)
    return obj


def case_graph_db_delete(obj):
    db.session.delete(obj)


def case_graph_db_commit():
    """Commit; False (rolled back) on an integrity error."""
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def case_graph_db_rollback():
    db.session.rollback()


# ------------------------------------------------------ Relation types --

def case_graph_db_relation_types():
    return CaseGraphRelationType.query.order_by(CaseGraphRelationType.sort_order,
                                                CaseGraphRelationType.id).all()


def case_graph_db_relation_type_get(relation_type_id):
    return CaseGraphRelationType.query.filter(CaseGraphRelationType.id == relation_type_id).first()


def case_graph_db_relation_type_by_name(name):
    return CaseGraphRelationType.query.filter(func.lower(CaseGraphRelationType.name) == name.lower()).first()


def case_graph_db_relation_type_usage(relation_type_id):
    return CaseGraphEdge.query.filter(CaseGraphEdge.relation_type_id == relation_type_id).count()


def case_graph_db_relation_type_usages():
    rows = (db.session.query(CaseGraphEdge.relation_type_id, func.count(CaseGraphEdge.edge_id))
            .group_by(CaseGraphEdge.relation_type_id).all())
    return {row[0]: row[1] for row in rows}


def case_graph_db_relation_type_max_sort():
    return db.session.query(func.max(CaseGraphRelationType.sort_order)).scalar()


