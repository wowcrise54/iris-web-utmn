#!/usr/bin/env python3

import requests


class OpenCTIClientError(Exception):
    pass


class OpenCTIClient:
    _SEARCH_QUERY = """
    query IrisOpenCTISearch($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            name
            description
            pattern
            pattern_type
            confidence
            x_opencti_score
            valid_from
            valid_until
            created_at
            updated_at
            objectLabel {
              edges {
                node {
                  value
                  color
                }
              }
            }
            objectMarking {
              edges {
                node {
                  definition
                  x_opencti_color
                }
              }
            }
            externalReferences {
              edges {
                node {
                  source_name
                  external_id
                  url
                }
              }
            }
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            observable_value
            description
            x_opencti_score
            created_at
            updated_at
            objectLabel {
              edges {
                node {
                  value
                  color
                }
              }
            }
            objectMarking {
              edges {
                node {
                  definition
                  x_opencti_color
                }
              }
            }
            externalReferences {
              edges {
                node {
                  source_name
                  external_id
                  url
                }
              }
            }
          }
        }
      }
    }
    """

    _MINIMAL_SEARCH_QUERY = """
    query IrisOpenCTISearchMinimal($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            name
            description
            pattern
            x_opencti_score
            confidence
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            standard_id
            entity_type
            observable_value
            description
            x_opencti_score
          }
        }
      }
    }
    """

    _BARE_SEARCH_QUERY = """
    query IrisOpenCTISearchBare($search: String!, $first: Int!) {
      indicators(search: $search, first: $first) {
        edges {
          node {
            id
            entity_type
            name
            pattern
          }
        }
      }
      stixCyberObservables(search: $search, first: $first) {
        edges {
          node {
            id
            entity_type
            observable_value
          }
        }
      }
    }
    """

    _HEALTH_QUERY = """
    query IrisOpenCTIHealthCheck {
      about {
        version
      }
    }
    """

    def __init__(self, url, token, verify_ssl=True, timeout=20, proxies=None):
        self.api_url = self._normalize_graphql_url(url)
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.proxies = proxies or {}
        self.session = requests.Session()

    @staticmethod
    def _normalize_graphql_url(url):
        if not url:
            return ""

        normalized = url.rstrip("/")
        if normalized.endswith("/graphql"):
            return normalized

        return f"{normalized}/graphql"

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def query(self, query, variables=None):
        if not self.api_url:
            raise OpenCTIClientError("OpenCTI URL is not configured")
        if not self.token:
            raise OpenCTIClientError("OpenCTI token is not configured")

        try:
            response = self.session.post(
                self.api_url,
                json={"query": query, "variables": variables or {}},
                headers=self._headers(),
                verify=self.verify_ssl,
                proxies=self.proxies,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise OpenCTIClientError(str(exc)) from exc

        if payload.get("errors"):
            raise OpenCTIClientError(str(payload["errors"]))

        return payload.get("data") or {}

    def health_check(self):
        return self.query(self._HEALTH_QUERY)

    def search_ioc(self, value, first=20):
        variables = {"search": value, "first": first}
        try:
            return self.query(self._SEARCH_QUERY, variables)
        except OpenCTIClientError as exc:
            if "Cannot query field" not in str(exc) and "Unknown argument" not in str(exc):
                raise

        try:
            return self.query(self._MINIMAL_SEARCH_QUERY, variables)
        except OpenCTIClientError as exc:
            if "Cannot query field" not in str(exc) and "Unknown argument" not in str(exc):
                raise

        return self.query(self._BARE_SEARCH_QUERY, variables)
