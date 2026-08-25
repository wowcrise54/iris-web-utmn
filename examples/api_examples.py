#!/usr/bin/env python3
"""
Complete examples for DFIR-IRIS and OpenCTI API integration

This script provides working examples for:
1. DFIR-IRIS REST API operations
2. OpenCTI GraphQL API operations
3. Combined workflows
"""

import requests
import time
from typing import Dict, List, Optional
from bs4 import BeautifulSoup


class DFIRIRISClient:
    """DFIR-IRIS REST API client"""
    
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.verify = verify_ssl
        
        if not verify_ssl:
            requests.packages.urllib3.disable_warnings()
        
        self._login(username, password)
    
    def _login(self, username: str, password: str):
        """Login to DFIR-IRIS"""
        # Get CSRF token
        resp = self.session.get(f'{self.base_url}/loginrmsedge')
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
        
        # Login
        data = {
            'email': username,
            'password': password,
            'csrf_token': csrf_token
        }
        
        resp = self.session.post(
            f'{self.base_url}/loginrmsedge',
            data=data
        )
        resp.raise_for_status()
        
        print(f"✓ Logged in as {username}")
    
    def _get_csrf_token(self) -> str:
        """Get fresh CSRF token"""
        resp = self.session.get(f'{self.base_url}/alerts')
        soup = BeautifulSoup(resp.text, 'html.parser')
        return soup.find('input', {'name': 'csrf_token'})['value']
    
    def list_alerts(self, page: int = 1, per_page: int = 10) -> Dict:
        """List alerts with pagination"""
        resp = self.session.get(
            f'{self.base_url}/alerts/filter',
            params={'page': page, 'per_page': per_page}
        )
        resp.raise_for_status()
        return resp.json()
    
    def create_alert(
        self,
        title: str,
        description: str,
        severity: str = 'Medium',
        customer_id: int = 1,
        ioc_value: str = None,
        ioc_type: str = None,
        ioc_tlp: str = 'AMBER',
        tags: str = None
    ) -> int:
        """Create a new alert"""
        csrf_token = self._get_csrf_token()
        
        data = {
            'csrf_token': csrf_token,
            'alert_title': title,
            'alert_description': description,
            'alert_severity': severity,
            'alert_status': 'New',
            'alert_customer_id': customer_id,
            'ioc_tlp': ioc_tlp
        }
        
        # Add IOC if provided
        if ioc_value and ioc_type:
            data['ioc_value'] = ioc_value
            data['ioc_type'] = ioc_type
        
        if tags:
            data['ioc_tags'] = tags
        
        resp = self.session.post(f'{self.base_url}/alerts/add', data=data)
        resp.raise_for_status()
        
        result = resp.json()
        alert_id = result['data']['alert_id']
        print(f"✓ Created alert #{alert_id}: {title}")
        
        return alert_id
    
    def get_alert(self, alert_id: int) -> Dict:
        """Get alert details"""
        resp = self.session.get(f'{self.base_url}/alerts/{alert_id}')
        resp.raise_for_status()
        return resp.json()['data']
    
    def add_ioc_to_alert(
        self,
        alert_id: int,
        ioc_value: str,
        ioc_type: str,
        ioc_tlp: str = 'AMBER',
        tags: str = None
    ):
        """Add IOC to existing alert"""
        csrf_token = self._get_csrf_token()
        
        data = {
            'csrf_token': csrf_token,
            'ioc_value': ioc_value,
            'ioc_type': ioc_type,
            'ioc_tlp': ioc_tlp
        }
        
        if tags:
            data['ioc_tags'] = tags
        
        resp = self.session.post(
            f'{self.base_url}/alerts/{alert_id}/iocs/add',
            data=data
        )
        resp.raise_for_status()
        
        print(f"✓ Added IOC {ioc_value} to alert #{alert_id}")
    
    def apply_opencti_recommendation(self, alert_id: int) -> Dict:
        """Apply OpenCTI recommendation to alert"""
        resp = self.session.post(
            f'{self.base_url}/alerts/{alert_id}/opencti/recommendation/apply'
        )
        resp.raise_for_status()
        
        result = resp.json()
        print(f"✓ Applied OpenCTI recommendation to alert #{alert_id}")
        return result
    
    def batch_update_alerts(
        self,
        alert_ids: List[int],
        field: str,
        value: str
    ):
        """Batch update multiple alerts"""
        csrf_token = self._get_csrf_token()
        
        data = {
            'csrf_token': csrf_token,
            'alert_ids': alert_ids,
            'field': field,
            'value': value
        }
        
        resp = self.session.post(
            f'{self.base_url}/alerts/batch/update',
            json=data
        )
        resp.raise_for_status()
        
        print(f"✓ Batch updated {len(alert_ids)} alerts")


class OpenCTIClient:
    """OpenCTI GraphQL API client"""
    
    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        })
        
        if not verify_ssl:
            requests.packages.urllib3.disable_warnings()
        
        self._validate_connection()
    
    def _validate_connection(self):
        """Validate connection to OpenCTI"""
        query = """
        query {
            me {
                id
                name
                email
            }
        }
        """
        
        resp = self.session.post(
            f'{self.base_url}/graphql',
            json={'query': query}
        )
        resp.raise_for_status()
        
        result = resp.json()
        if 'data' in result and 'me' in result['data']:
            user = result['data']['me']
            print(f"✓ Connected to OpenCTI as {user['name']}")
        else:
            raise Exception(f"Failed to connect to OpenCTI: {result}")
    
    def query(self, query: str, variables: Dict = None) -> Dict:
        """Execute GraphQL query"""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables
        
        resp = self.session.post(
            f'{self.base_url}/graphql',
            json=payload
        )
        resp.raise_for_status()
        
        result = resp.json()
        if 'errors' in result:
            raise Exception(f"GraphQL error: {result['errors']}")
        
        return result['data']
    
    def search_ioc(
        self,
        ioc_value: str,
        ioc_type: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """Search for IOC in OpenCTI"""
        
        type_mapping = {
            'ipv4-addr': 'IPv4-Addr',
            'ipv6-addr': 'IPv6-Addr',
            'domain-name': 'Domain-Name',
            'url': 'Url',
            'email-addr': 'Email-Addr',
            'md5': 'StixFile',
            'sha-256': 'StixFile'
        }
        
        entity_type = type_mapping.get(ioc_type) if ioc_type else None
        
        query = """
        query SearchIOC($search: String!, $types: [String]) {
            stixCyberObservables(
                search: $search
                types: $types
                first: $limit
            ) {
                edges {
                    node {
                        id
                        observable_value
                        entity_type
                        x_opencti_score
                        confidence
                        description
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
        """
        
        variables = {
            "search": ioc_value,
            "types": [entity_type] if entity_type else None,
            "limit": limit
        }
        
        result = self.query(query, variables)
        return result.get('stixCyberObservables', {}).get('edges', [])
    
    def get_indicator_by_id(self, indicator_id: str) -> Dict:
        """Get indicator by ID"""
        query = """
        query GetIndicator($id: ID!) {
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
        """
        
        result = self.query(query, {'id': indicator_id})
        return result.get('indicator')
    
    def create_indicator(
        self,
        name: str,
        pattern: str,
        pattern_type: str = 'stix',
        score: int = None,
        confidence: int = None,
        labels: List[str] = None,
        description: str = None
    ) -> Dict:
        """Create new indicator"""
        
        mutation = """
        mutation CreateIndicator(
            $name: String!
            $pattern: String!
            $patternType: String!
            $x_opencti_score: Int
            $confidence: Int
            $labels: [String]
            $description: String
        ) {
            indicatorAdd(
                input: {
                    name: $name
                    pattern: $pattern
                    pattern_type: $patternType
                    x_opencti_score: $x_opencti_score
                    confidence: $confidence
                    labels: $labels
                    description: $description
                }
            ) {
                id
                name
                pattern
                x_opencti_score
                confidence
            }
        }
        """
        
        variables = {
            "name": name,
            "pattern": pattern,
            "patternType": pattern_type,
            "x_opencti_score": score,
            "confidence": confidence,
            "labels": labels,
            "description": description
        }
        
        result = self.query(mutation, variables)
        indicator = result.get('indicatorAdd')
        print(f"✓ Created indicator: {name} (ID: {indicator['id']})")
        return indicator
    
    def create_observable(
        self,
        observable_type: str,
        value: str,
        score: int = None,
        confidence: int = None
    ) -> Dict:
        """Create new observable (IOC)"""
        
        mutation = """
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
        """
        
        variables = {
            "type": observable_type,
            "value": value,
            "x_opencti_score": score,
            "confidence": confidence
        }
        
        result = self.query(mutation, variables)
        observable = result.get('stixCyberObservableAdd')
        print(f"✓ Created observable: {value} (ID: {observable['id']})")
        return observable
    
    def update_indicator(
        self,
        indicator_id: str,
        score: int = None,
        confidence: int = None,
        labels: List[str] = None
    ):
        """Update indicator"""
        
        edits = []
        if score is not None:
            edits.append({"key": "x_opencti_score", "value": score})
        if confidence is not None:
            edits.append({"key": "confidence", "value": confidence})
        if labels is not None:
            edits.append({"key": "labels", "value": labels})
        
        if not edits:
            return
        
        mutation = """
        mutation UpdateIndicator($id: ID!, $input: [EditInput]!) {
            indicatorEdit(id: $id) {
                fieldPatch(input: $input) {
                    id
                    x_opencti_score
                    confidence
                }
            }
        }
        """
        
        self.query(mutation, {'id': indicator_id, 'input': edits})
        print(f"✓ Updated indicator: {indicator_id}")
    
    def delete_indicator(self, indicator_id: str):
        """Delete indicator"""
        mutation = """
        mutation DeleteIndicator($id: ID!) {
            indicatorEdit(id: $id) {
                delete
            }
        }
        """
        
        self.query(mutation, {'id': indicator_id})
        print(f"✓ Deleted indicator: {indicator_id}")
    
    def search_indicators(
        self,
        search: str = None,
        filters: Dict = None,
        limit: int = 10
    ) -> List[Dict]:
        """Search indicators with filters"""
        
        query = """
        query SearchIndicators($search: String, $filters: FilterGroup, $first: Int) {
            indicators(
                search: $search
                filters: $filters
                first: $first
            ) {
                edges {
                    node {
                        id
                        name
                        pattern
                        x_opencti_score
                        confidence
                        created
                        modified
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
            "search": search,
            "filters": filters,
            "first": limit
        }
        
        result = self.query(query, variables)
        return result.get('indicators', {}).get('edges', [])


# ============================================================================
# EXAMPLES
# ============================================================================

def example_1_iris_create_alert():
    """Example 1: Create alert in DFIR-IRIS"""
    print("\n=== Example 1: Create Alert in DFIR-IRIS ===\n")
    
    iris = DFIRIRISClient(
        base_url='https://localhost',
        username='administrator',
        password='TestPass123'
    )
    
    # Create alert with IOC
    alert_id = iris.create_alert(
        title='Test Alert - Malicious IP',
        description='Alert for testing OpenCTI integration',
        severity='High',
        ioc_value='185.220.101.1',
        ioc_type='ipv4-addr',
        tags='test,opencti'
    )
    
    # Add another IOC
    iris.add_ioc_to_alert(
        alert_id=alert_id,
        ioc_value='8.8.8.8',
        ioc_type='ipv4-addr',
        tags='dns'
    )
    
    print(f"\nAlert created with ID: {alert_id}")


def example_2_opencti_search():
    """Example 2: Search IOC in OpenCTI"""
    print("\n=== Example 2: Search IOC in OpenCTI ===\n")
    
    opencti = OpenCTIClient(
        base_url='http://10.252.205.99:8080',
        api_key='YOUR_API_KEY_HERE'
    )
    
    # Search for IP
    results = opencti.search_ioc('185.220.101.1', 'ipv4-addr')
    
    print(f"Found {len(results)} results:")
    for edge in results:
        node = edge['node']
        print(f"  - {node['observable_value']}")
        print(f"    Score: {node.get('x_opencti_score', 'N/A')}")
        print(f"    Confidence: {node.get('confidence', 'N/A')}")
        if node.get('labels', {}).get('edges'):
            labels = [e['node']['name'] for e in node['labels']['edges']]
            print(f"    Labels: {', '.join(labels)}")


def example_3_opencti_create_indicator():
    """Example 3: Create indicator in OpenCTI"""
    print("\n=== Example 3: Create Indicator in OpenCTI ===\n")
    
    opencti = OpenCTIClient(
        base_url='http://10.252.205.99:8080',
        api_key='YOUR_API_KEY_HERE'
    )
    
    # Create indicator
    indicator = opencti.create_indicator(
        name='Malicious IP 185.220.101.1',
        pattern="[ipv4-addr:value = '185.220.101.1']",
        pattern_type='stix',
        score=80,
        confidence=75,
        labels=['malicious', 'threat-intel'],
        description='Known malicious IP address'
    )
    
    print(f"\nIndicator created: {indicator['id']}")


def example_4_combined_workflow():
    """Example 4: Combined DFIR-IRIS + OpenCTI workflow"""
    print("\n=== Example 4: Combined Workflow ===\n")
    
    # Initialize clients
    iris = DFIRIRISClient(
        base_url='https://localhost',
        username='administrator',
        password='TestPass123'
    )
    
    opencti = OpenCTIClient(
        base_url='http://10.252.205.99:8080',
        api_key='YOUR_API_KEY_HERE'
    )
    
    # Step 1: Create alert in DFIR-IRIS
    print("Step 1: Creating alert in DFIR-IRIS...")
    alert_id = iris.create_alert(
        title='New Threat - Suspicious IP',
        description='Alert created for suspicious IP analysis',
        severity='Medium',
        ioc_value='185.220.101.1',
        ioc_type='ipv4-addr',
        tags='new,investigation'
    )
    
    # Step 2: Search IOC in OpenCTI
    print("\nStep 2: Searching IOC in OpenCTI...")
    results = opencti.search_ioc('185.220.101.1', 'ipv4-addr')
    
    if results:
        print(f"Found {len(results)} matching indicators")
        
        # Step 3: Create indicator if not exists
        if len(results) == 0:
            print("\nStep 3: Creating new indicator in OpenCTI...")
            opencti.create_indicator(
                name='Suspicious IP 185.220.101.1',
                pattern="[ipv4-addr:value = '185.220.101.1']",
                pattern_type='stix',
                score=60,
                confidence=50,
                labels=['suspicious'],
                description='Suspicious IP from DFIR-IRIS alert'
            )
    
    # Step 4: Apply OpenCTI recommendation
    print("\nStep 4: Applying OpenCTI recommendation...")
    try:
        result = iris.apply_opencti_recommendation(alert_id)
        print(f"Recommendation applied: {result}")
    except Exception as e:
        print(f"Note: {e}")
    
    print(f"\nWorkflow complete for alert #{alert_id}")


def example_5_batch_operations():
    """Example 5: Batch operations"""
    print("\n=== Example 5: Batch Operations ===\n")
    
    iris = DFIRIRISClient(
        base_url='https://localhost',
        username='administrator',
        password='TestPass123'
    )
    
    # Create multiple alerts
    print("Creating 3 test alerts...")
    alert_ids = []
    for i in range(3):
        alert_id = iris.create_alert(
            title=f'Test Alert #{i+1}',
            description=f'Test alert number {i+1}',
            severity='Low'
        )
        alert_ids.append(alert_id)
    
    # Batch update all alerts
    print("\nBatch updating all alerts to status: Closed")
    iris.batch_update_alerts(alert_ids, 'alert_status', 'Closed')
    
    print(f"\nBatch operations complete for alerts: {alert_ids}")


if __name__ == '__main__':
    print("=" * 60)
    print("DFIR-IRIS & OpenCTI API Examples")
    print("=" * 60)
    
    # Uncomment examples to run:
    # example_1_iris_create_alert()
    # example_2_opencti_search()
    # example_3_opencti_create_indicator()
    # example_4_combined_workflow()
    # example_5_batch_operations()
    
    print("\nAvailable examples:")
    print("  1. example_1_iris_create_alert()")
    print("  2. example_2_opencti_search()")
    print("  3. example_3_opencti_create_indicator()")
    print("  4. example_4_combined_workflow()")
    print("  5. example_5_batch_operations()")
    
    print("\nTo run an example, uncomment the corresponding line at the bottom of the file.")
