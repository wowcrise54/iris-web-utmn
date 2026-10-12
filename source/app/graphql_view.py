"""GraphQL HTTP execution using the same schema and protocol as IRIS."""
from functools import partial

from graphql import GraphQLError, GraphQLSchema, specified_rules
from graphql_server import (HttpQueryError, encode_execution_results,
                            format_error_default, json_encode, load_json_body,
                            run_http_query)

from .web import Response, request


class GraphQLView:
    @classmethod
    def as_view(cls, name, *, schema):
        native_schema = schema if isinstance(schema, GraphQLSchema) else schema.graphql_schema

        def view():
            try:
                if request.mimetype == "application/graphql":
                    data = {"query": request.get_data(as_text=True)}
                elif request.mimetype == "application/json":
                    data = load_json_body(request.get_data(as_text=True))
                elif request.mimetype in ("application/x-www-form-urlencoded", "multipart/form-data"):
                    data = request.form
                else:
                    data = {}
                results, _ = run_http_query(
                    native_schema, request.method.lower(), data,
                    query_data=request.args, context_value={"request": request},
                    validation_rules=specified_rules,
                )
                body, status = encode_execution_results(
                    results, is_batch=isinstance(data, list),
                    encode=partial(json_encode, pretty=bool(request.args.get("pretty"))),
                )
                return Response(body, status=status, content_type="application/json")
            except HttpQueryError as exc:
                body = json_encode({"errors": [format_error_default(GraphQLError(exc.message))]})
                return Response(body, status=exc.status_code, headers=exc.headers, content_type="application/json")

        view.__name__ = name
        return view
