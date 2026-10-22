"""Relation endpoint contract from OpenCTI 7.260902.0's public schema.

Source: OpenCTI-Platform/opencti, config/schema/opencti.graphql at tag 7.260902.0.
Install the module's test extra to run GraphQL validation locally.
"""
import unittest

from iris_opencti_module.client import RELATION_QUERY

try:
    from graphql import build_schema, parse, validate
except ImportError:
    build_schema = None


@unittest.skipUnless(build_schema, 'graphql-core test dependency not installed')
class RelationSchemaTests(unittest.TestCase):
    def test_relation_query_accepts_union_endpoints(self):
        # Unrelated fields/types are omitted; union endpoint semantics are retained.
        schema = build_schema('''
            interface StixObject { id: ID! entity_type: String! }
            interface StixRelationship { id: ID! entity_type: String! }
            type Malware implements StixObject { id: ID! entity_type: String! name: String }
            type Tool implements StixObject { id: ID! entity_type: String! name: String }
            type Campaign implements StixObject { id: ID! entity_type: String! name: String }
            type IntrusionSet implements StixObject { id: ID! entity_type: String! name: String }
            type AttackPattern implements StixObject { id: ID! entity_type: String! name: String }
            type ThreatActorGroup implements StixObject { id: ID! entity_type: String! name: String }
            type Creator { id: ID! entity_type: String! }
            union StixObjectOrStixRelationshipOrCreator = Malware | Tool | Campaign |
                IntrusionSet | AttackPattern | ThreatActorGroup | StixCoreRelationship | Creator
            type StixCoreRelationship implements StixRelationship {
                id: ID! entity_type: String! relationship_type: String
                from: StixObjectOrStixRelationshipOrCreator
                to: StixObjectOrStixRelationshipOrCreator
            }
            type Edge { node: StixCoreRelationship }
            type PageInfo { hasNextPage: Boolean! endCursor: ID }
            type Connection { edges: [Edge] pageInfo: PageInfo! }
            type Query {
                stixCoreRelationships(fromOrToId: [String], first: Int, after: ID): Connection
            }
        ''')
        errors = validate(schema, parse(RELATION_QUERY))
        self.assertEqual([error.message for error in errors], [])
