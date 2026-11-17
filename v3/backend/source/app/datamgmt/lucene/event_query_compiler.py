"""Compile the text fields supported by case timeline Lucene search."""

from sqlalchemy import or_

from app.datamgmt.filtering import LIKE_ESCAPE_CHARACTER
from app.datamgmt.lucene.query_compiler import LuceneQueryCompiler
from app.datamgmt.lucene.query_compiler import _substring_pattern
from app.datamgmt.lucene.query_parser import TermValue
from app.datamgmt.lucene.query_parser import lucene_parse
from app.models.cases import CasesEvent
from app.models.errors import SearchQueryError


_EVENT_FIELDS = {
    'title': 'event_title',
    'description': 'event_content',
    'source': 'event_source',
    'tag': 'event_tags',
}


class EventQueryCompiler(LuceneQueryCompiler):
    def _compile_clause(self, node):
        if node.field is not None and node.field not in _EVENT_FIELDS:
            raise SearchQueryError(f"Unknown event field '{node.field}'", node.position)
        if not isinstance(node.value, TermValue):
            raise SearchQueryError('Comparisons and ranges are unavailable for event text fields',
                                   node.value.position)

        columns = _EVENT_FIELDS.values() if node.field is None else (_EVENT_FIELDS[node.field],)
        pattern = _substring_pattern(node.value)
        return or_(*(getattr(CasesEvent, column).ilike(pattern, escape=LIKE_ESCAPE_CHARACTER)
                     for column in columns))


def compile_event_query(query):
    node = lucene_parse(query)
    return EventQueryCompiler().compile(node) if node is not None else None
