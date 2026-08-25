# DFIR-IRIS & OpenCTI API Reference Guide

> **Complete API documentation for DFIR-IRIS v2.4.27 and OpenCTI latest**
> 
> This guide provides comprehensive coverage of both DFIR-IRIS REST API and OpenCTI GraphQL API.

---

## Table of Contents

1. [DFIR-IRIS REST API](#dfir-iris-rest-api)
   - [Authentication](#authentication)
   - [Alerts API](#alerts-api)
   - [IOCs API](#iocs-api)
   - [OpenCTI Integration API](#opencti-integration-api)
   - [Cases API](#cases-api)
   - [Customers API](#customers-api)
   - [Modules API](#modules-api)
2. [OpenCTI GraphQL API](#opencti-graphql-api)
   - [Authentication](#authentication-1)
   - [Queries](#queries)
   - [Mutations](#mutations)
   - [Subscriptions](#subscriptions)
   - [Filters](#filters)
   - [Indicator/IOC Operations](#indicatorioc-operations)
3. [Integration Examples](#integration-examples)
4. [Error Handling](#error-handling)
5. [Rate Limiting](#rate-limiting)

---

## DFIR-IRIS REST API

### Authentication

DFIR-IRIS uses session-based authentication with CSRF protection.

**Headers required:**
```
Content-Type: application/json
X-CSRF-Token: <token>
```

**CSRF Token Acquisition:**
```python
import requests

session = requests.Session()
# Get CSRF token from login page
resp = session.get('https://localhost/login')
csrf_token = resp.cookies.get('csrf_token')

# Or extract from page HTML
from bs4 import BeautifulSoup
soup = BeautifulSoup(resp.text, 'html.parser')
csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
```

**Login:**
```python
# POST to /loginrmsedge
data = {
    'email': 'administrator@iris.local',
    'password': 'TestPass123',
    'csrf_token': csrf_token
}
resp = session.post('https://localhost/loginrmsedge', data=data)
```

---

### Alerts API

#### List Alerts
```
GET /alerts/filter
```

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `per_page` (int): Items per page (default: 10)
- `alert_ids` (str): Comma-separated alert IDs
- `alert_assets` (str): Comma-separated asset names
- `caseid` (int): Case ID filter

**Example:**
```python
resp = session.get('https://localhost/alerts/filter?page=1&per_page=20')
alerts = resp.json()['data']['alerts']
```

#### Create Alert
```
POST /alerts/add
```

**Request Body (Form Data):**
```python
data = {
    'csrf_token': csrf_token,
    'alert_title': 'Test Alert - OpenCTI Enrichment',
    'alert_description': 'Alert created for testing',
    'alert_severity': 'High',
    'alert_status': 'New',
    'alert_customer_id': 1,
    'ioc_value': '185.220.101.1',
    'ioc_type': 'ipv4-addr',
    'ioc_tlp': 'AMBER',
    'ioc_tags': 'tag1,tag2'
}

resp = session.post('https://localhost/alerts/add', data=data)
```

**Response:**
```json
{
    "status": "success",
    "message": "Alert created successfully",
    "data": {
        "alert_id": 3,
        "alert_uuid": "uuid-here"
    }
}
```

#### Get Alert Details
```
GET /alerts/<alert_id>
```

**Example:**
```python
resp = session.get('https://localhost/alerts/3')
alert = resp.json()['data']
```

#### Update Alert
```
POST /alerts/<alert_id>/edit
```

**Request Body:**
```python
data = {
    'csrf_token': csrf_token,
    'alert_title': 'Updated Title',
    'alert_description': 'Updated description',
    'alert_severity': 'Critical',
    'alert_status': 'Open'
}

resp = session.post(f'https://localhost/alerts/{alert_id}/edit', data=data)
```

#### Delete Alert
```
DELETE /alerts/<alert_id>
```

**Example:**
```python
resp = session.delete(f'https://localhost/alerts/{alert_id}')
```

#### Batch Update Alerts
```
POST /alerts/batch/update
```

**Request Body:**
```python
data = {
    'csrf_token': csrf_token,
    'alert_ids': [1, 2, 3],
    'field': 'alert_status',
    'value': 'Closed'
}

resp = session.post('https://localhost/alerts/batch/update', json=data)
```

---

### IOCs API

#### Add IOC to Alert
```
POST /alerts/<alert_id>/iocs/add
```

**Request Body:**
```python
data = {
    'csrf_token': csrf_token,
    'ioc_value': '8.8.8.8',
    'ioc_type': 'ipv4-addr',
    'ioc_tlp': 'GREEN',
    'ioc_tags': 'dns,google'
}

resp = session.post(f'https://localhost/alerts/{alert_id}/iocs/add', data=data)
```

#### List Alert IOCs
```
GET /alerts/<alert_id>/iocs
```

**Example:**
```python
resp = session.get(f'https://localhost/alerts/{alert_id}/iocs')
iocs = resp.json()['data']['iocs']
```

#### Update IOC
```
POST /alerts/<alert_id>/iocs/<ioc_id>/edit
```

#### Delete IOC
```
DELETE /alerts/<alert_id>/iocs/<ioc_id>
```

---

### OpenCTI Integration API

#### Trigger Manual Enrichment
```
POST /alerts/<alert_id>/opencti/recommendation/apply
```

**Description:** Apply OpenCTI recommendation to alert

**Example:**
```python
resp = session.post(f'https://localhost/alerts/{alert_id}/opencti/recommendation/apply')
```

**Response:**
```json
{
    "status": "success",
    "message": "OpenCTI recommendation applied",
    "data": {
        "severity": "High",
        "risk_score": 75
    }
}
```

#### Get OpenCTI Progress (WebSocket)
```
WebSocket: /opencti
```

**Events:**
- `join_enrichment`: Join enrichment room
- `leave_enrichment`: Leave enrichment room
- `enrichment_progress`: Progress updates

**Example:**
```python
from flask_socketio import SocketIOClient

socket = SocketIOClient()
socket.connect('https://localhost', namespaces='/opencti')
socket.emit('join_enrichment', {'alert_id': alert_id})

@socket.on('enrichment_progress', namespace='/opencti')
def handle_progress(data):
    print(f"Progress: {data['progress']}")
```

#### Get OpenCTI Metrics
```
GET /api/opencti/metrics?time_range=24h
```

**Response:**
```json
{
    "enrichment": {
        "total": 150,
        "successful": 142,
        "failed": 8,
        "avg_duration": 0.5
    },
    "cache": {
        "hits": 120,
        "misses": 30,
        "hit_rate": 0.8
    }
}
```

---

### Cases API

#### Create Case from Alert
```
POST /alerts/<alert_id>/create_case
```

**Request Body:**
```python
data = {
    'csrf_token': csrf_token,
    'case_title': 'Case from Alert',
    'case_description': 'Auto-created case'
}

resp = session.post(f'https://localhost/alerts/{alert_id}/create_case', data=data)
```

#### List Cases
```
GET /cases/filter
```

---

### Customers API

#### List Customers
```
GET /manage/customers/list
```

#### Get Customer Details
```
GET /manage/customers/<customer_id>
```

---

### Modules API

#### List Modules
```
GET /manage/modules/list
```

#### Enable/Disable Module
```
POST /manage/modules/<module_id>/toggle
```

---

## OpenCTI GraphQL API

### Authentication

OpenCTI uses API key authentication.

**Headers required:**
```
Content-Type: application/json
Authorization: Bearer <API_KEY>
```

**Example:**
```python
import requests

headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer <YOUR_API_KEY>'
}

query = """
{
    me {
        id
        name
        email
    }
}
"""

resp = requests.post(
    'http://10.252.205.99:8080/graphql',
    json={'query': query},
    headers=headers
)

user = resp.json()['data']['me']
```

---

### Queries

#### Get Current User
```graphql
query {
    me {
        id
        name
        email
        roles {
            id
            name
        }
    }
}
```

#### Search Indicators
```graphql
query SearchIndicators($search: String!, $filters: FilterGroup) {
    indicators(
        search: $search
        filters: $filters
        first: 10
    ) {
        edges {
            node {
                id
                name
                description
                pattern
                pattern_type
                x_opencti_score
                confidence
                labels {
                    edges {
                        node {
                            id
                            name
                        }
                    }
                }
                created
                modified
            }
        }
    }
}
```

**Usage:**
```python
query = """
query SearchIndicators($search: String!, $filters: FilterGroup) {
    indicators(
        search: $search
        filters: $filters
        first: 10
    ) {
        edges {
            node {
                id
                name
                x_opencti_score
                confidence
            }
        }
    }
}
"""

variables = {
    "search": "8.8.8.8",
    "filters": {
        "mode": "and",
        "filters": [{
            "key": "entity_type",
            "values": ["Indicator"],
            "operator": "eq",
            "mode": "or"
        }],
        "filterGroups": []
    }
}

resp = requests.post(
    'http://10.252.205.99:8080/graphql',
    json={'query': query, 'variables': variables},
    headers=headers
)
```

#### Get Indicator by ID
```graphql
query GetIndicator($id: String!) {
    indicator(id: $id) {
        id
        name
        description
        pattern
        pattern_type
        x_opencti_score
        confidence
        created
        modified
        labels {
            edges {
                node {
                    id
                    name
                }
            }
        }
    }
}
```

#### Search IOCs (StixCyberObservable)
```graphql
query SearchIOCs($search: String!) {
    stixCyberObservables(
        search: $search
        first: 10
    ) {
        edges {
            node {
                id
                observable_value
                entity_type
                x_opencti_score
                confidence
            }
        }
    }
}
```

#### List All Indicators
```graphql
query ListIndicators {
    indicators(first: 100) {
        edges {
            node {
                id
                name
                pattern
                x_opencti_score
                confidence
                labels {
                    edges {
                        node {
                            name
                        }
                    }
                }
            }
        }
    }
}
```

---

### Mutations

#### Create Indicator
```graphql
mutation CreateIndicator(
    $name: String!
    $pattern: String!
    $patternType: String!
    $x_opencti_score: Int
    $confidence: Int
    $labels: [String]
) {
    indicatorAdd(
        input: {
            name: $name
            pattern: $pattern
            pattern_type: $patternType
            x_opencti_score: $x_opencti_score
            confidence: $confidence
            labels: $labels
        }
    ) {
        id
        name
        pattern
        x_opencti_score
        confidence
    }
}
```

**Usage:**
```python
mutation = """
mutation CreateIndicator(
    $name: String!
    $pattern: String!
    $patternType: String!
    $x_opencti_score: Int
    $confidence: Int
    $labels: [String]
) {
    indicatorAdd(
        input: {
            name: $name
            pattern: $pattern
            pattern_type: $patternType
            x_opencti_score: $x_opencti_score
            confidence: $confidence
            labels: $labels
        }
    ) {
        id
        name
        pattern
    }
}
"""

variables = {
    "name": "Malicious IP",
    "pattern": "[ipv4-addr:value = '185.220.101.1']",
    "patternType": "stix",
    "x_opencti_score": 80,
    "confidence": 75,
    "labels": ["malicious", "threat-intel"]
}

resp = requests.post(
    'http://10.252.205.99:8080/graphql',
    json={'query': mutation, 'variables': variables},
    headers=headers
)
```

#### Update Indicator
```graphql
mutation UpdateIndicator($id: ID!, $input: [EditInput]!) {
    indicatorEdit(id: $id) {
        fieldPatch(input: $input) {
            id
            name
            x_opencti_score
        }
    }
}
```

#### Delete Indicator
```graphql
mutation DeleteIndicator($id: ID!) {
    indicatorEdit(id: $id) {
        delete
    }
}
```

#### Create Observable (IOC)
```graphql
mutation CreateObservable(
    $type: String!
    $value: String!
    $x_opencti_score: Int
    $confidence: Int
) {
    stixCyberObservableAdd(
        input: {
            type: $type
            value: $value
            x_opencti_score: $x_opencti_score
            confidence: $confidence
        }
    ) {
        id
        observable_value
        entity_type
        x_opencti_score
    }
}
```

---

### Filters

OpenCTI supports advanced filtering with the following operators:

**Operators:**
- `eq` - Equal to
- `not_eq` - Not equal to
- `gt` - Greater than
- `gte` - Greater than or equal
- `lt` - Less than
- `lte` - Less than or equal
- `match` - Full-text match
- `wildcard` - Wildcard match

**Modes:**
- `and` - All filters must match
- `or` - Any filter can match

**Example Filter:**
```python
filters = {
    "mode": "and",
    "filters": [
        {
            "key": "entity_type",
            "values": ["Indicator"],
            "operator": "eq",
            "mode": "or"
        },
        {
            "key": "x_opencti_score",
            "values": [50],
            "operator": "gte",
            "mode": "or"
        },
        {
            "key": "labels",
            "values": ["malicious"],
            "operator": "eq",
            "mode": "or"
        }
    ],
    "filterGroups": []
}
```

---

### Indicator/IOC Operations

#### Search by Value
```python
def search_ioc(client, ioc_value, ioc_type):
    """Search for an IOC in OpenCTI"""
    
    # Map IOC type to OpenCTI entity type
    type_mapping = {
        'ipv4-addr': 'IPv4-Addr',
        'ipv6-addr': 'IPv6-Addr',
        'domain-name': 'Domain-Name',
        'url': 'Url',
        'email-addr': 'Email-Addr',
        'file-hash': 'StixFile'
    }
    
    entity_type = type_mapping.get(ioc_type, ioc_type)
    
    query = """
    query SearchIOC($search: String!, $types: [String]) {
        stixCyberObservables(
            search: $search
            types: $types
            first: 10
        ) {
            edges {
                node {
                    id
                    observable_value
                    entity_type
                    x_opencti_score
                    confidence
                    labels {
                        edges {
                            node {
                                name
                            }
                        }
                    }
                }
            }
        }
    }
    """
    
    variables = {
        "search": ioc_value,
        "types": [entity_type]
    }
    
    resp = client.post('/graphql', json={
        'query': query,
        'variables': variables
    })
    
    return resp.json()['data']['stixCyberObservables']
```

#### Get Similar IOCs
```python
def get_similar_iocs(client, ioc_value):
    """Get similar IOCs based on value"""
    
    query = """
    query SimilarIOCs($search: String!) {
        stixCyberObservables(
            search: $search
            first: 20
        ) {
            edges {
                node {
                    id
                    observable_value
                    entity_type
                    x_opencti_score
                    confidence
                    created
                    modified
                }
            }
        }
    }
    """
    
    variables = {"search": ioc_value}
    
    resp = client.post('/graphql', json={
        'query': query,
        'variables': variables
    })
    
    return resp.json()['data']['stixCyberObservables']
```

---

## Integration Examples

### Complete Workflow: DFIR-IRIS → OpenCTI

```python
import requests
from bs4 import BeautifulSoup

class DFIRIRISOpenCTIIntegration:
    def __init__(self, iris_url, iris_user, iris_pass, 
                 opencti_url, opencti_token):
        self.iris_url = iris_url
        self.opencti_url = opencti_url
        self.opencti_token = opencti_token
        
        # Login to DFIR-IRIS
        self.iris_session = requests.Session()
        self._iris_login(iris_user, iris_pass)
    
    def _iris_login(self, user, password):
        """Login to DFIR-IRIS"""
        resp = self.iris_session.get(f'{self.iris_url}/loginrmsedge')
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
        
        data = {
            'email': user,
            'password': password,
            'csrf_token': csrf_token
        }
        
        self.iris_session.post(
            f'{self.iris_url}/loginrmsedge',
            data=data
        )
    
    def create_alert_with_ioc(self, title, ioc_value, ioc_type, severity='High'):
        """Create alert with IOC in DFIR-IRIS"""
        
        resp = self.iris_session.get(f'{self.iris_url}/alerts')
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
        
        data = {
            'csrf_token': csrf_token,
            'alert_title': title,
            'alert_description': f'Alert for IOC: {ioc_value}',
            'alert_severity': severity,
            'alert_status': 'New',
            'ioc_value': ioc_value,
            'ioc_type': ioc_type,
            'ioc_tlp': 'AMBER'
        }
        
        resp = self.iris_session.post(
            f'{self.iris_url}/alerts/add',
            data=data
        )
        
        return resp.json()['data']['alert_id']
    
    def enrich_ioc_with_opencti(self, ioc_value, ioc_type):
        """Enrich IOC using OpenCTI"""
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.opencti_token}'
        }
        
        query = """
        query SearchIOC($search: String!, $types: [String]) {
            stixCyberObservables(
                search: $search
                types: $types
                first: 10
            ) {
                edges {
                    node {
                        id
                        observable_value
                        entity_type
                        x_opencti_score
                        confidence
                        labels {
                            edges {
                                node {
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        type_mapping = {
            'ipv4-addr': 'IPv4-Addr',
            'domain-name': 'Domain-Name',
            'url': 'Url'
        }
        
        variables = {
            "search": ioc_value,
            "types": [type_mapping.get(ioc_type, ioc_type)]
        }
        
        resp = requests.post(
            f'{self.opencti_url}/graphql',
            json={'query': query, 'variables': variables},
            headers=headers
        )
        
        return resp.json()['data']['stixCyberObservables']
    
    def apply_opencti_recommendation(self, alert_id, recommendation):
        """Apply OpenCTI recommendation to DFIR-IRIS alert"""
        
        resp = self.iris_session.get(f'{self.iris_url}/alerts/{alert_id}')
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
        
        data = {
            'csrf_token': csrf_token,
            'severity': recommendation['severity'],
            'risk_score': recommendation['risk_score']
        }
        
        resp = self.iris_session.post(
            f'{self.iris_url}/alerts/{alert_id}/opencti/recommendation/apply',
            json=data
        )
        
        return resp.json()
```

---

## Error Handling

### DFIR-IRIS Errors
```json
{
    "status": "error",
    "message": "Error message here"
}
```

### OpenCTI Errors
```json
{
    "errors": [
        {
            "message": "Error message",
            "locations": [{"line": 1, "column": 1}],
            "path": ["field"]
        }
    ]
}
```

**Common Errors:**
- `401 Unauthorized`: Invalid API key or session
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict (e.g., stale recommendation)
- `422 Unprocessable Entity`: Validation error

---

## Rate Limiting

### DFIR-IRIS
- No explicit rate limiting
- CSRF protection required for all state-changing operations
- Session-based authentication

### OpenCTI
- Default: 100 requests per minute per API key
- Configurable in `config.yml`
- Rate limit headers in response:
  ```
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 95
  X-RateLimit-Reset: 1640000000
  ```

---

## Best Practices

### DFIR-IRIS
1. Always use CSRF tokens for POST/PUT/DELETE operations
2. Use session management for multiple requests
3. Handle pagination for large result sets
4. Use batch operations for bulk updates
5. Cache CSRF tokens when possible

### OpenCTI
1. Use variables instead of string interpolation
2. Request only needed fields to reduce payload size
3. Implement retry logic for transient failures
4. Use pagination for large datasets
5. Cache frequently queried data

---

## Quick Reference

### Common IOC Types
| Type | DFIR-IRIS | OpenCTI |
|------|-----------|---------|
| IPv4 | `ipv4-addr` | `IPv4-Addr` |
| IPv6 | `ipv6-addr` | `IPv6-Addr` |
| Domain | `domain-name` | `Domain-Name` |
| URL | `url` | `Url` |
| Email | `email-addr` | `Email-Addr` |
| MD5 | `md5` | `StixFile` |
| SHA-256 | `sha256` | `StixFile` |

### Common Severity Levels
- Low
- Medium
- High
- Critical

### Common TLP Levels
- GREEN
- AMBER
- AMBER+STRICT
- RED

---

**Version:** 1.0  
**Last Updated:** 2026-08-25  
**DFIR-IRIS Version:** 2.4.27  
**OpenCTI Version:** Latest
