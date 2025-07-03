"""
Test configuration and fixtures for Redeban KYC Lambda tests.

This module provides:
- Common test fixtures
- Mock configurations
- Test utilities and helpers
- Environment setup for testing

Author: DevSecOps Team
Version: 1.0.0
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Configure test environment
os.environ.update({
    'AWS_REGION': 'us-east-1',
    'DYNAMODB_TABLE': 'RedebanTokens-test',
    'SECRET_NAME': 'Redeban_Obtener_Token',
    'TOKEN_LAMBDA_NAME': 'lambda_function_obtener_token',
    'LOG_LEVEL': 'INFO',
    'ENVIRONMENT': 'test'
})


class MockLambdaContext:
    """Mock AWS Lambda context for testing."""

    def __init__(self,
                 aws_request_id: str = "test-request-123",
                 function_name: str = "test-function",
                 memory_limit_mb: int = 1024,
                 remaining_time_ms: int = 30000):
        self.aws_request_id = aws_request_id
        self.function_name = function_name
        self.memory_limit_in_mb = memory_limit_mb
        self.function_version = "$LATEST"
        self._remaining_time_ms = remaining_time_ms

    def get_remaining_time_in_millis(self) -> int:
        return self._remaining_time_ms


@pytest.fixture
def lambda_context():
    """Fixture providing a mock Lambda context."""
    return MockLambdaContext()


@pytest.fixture
def sample_commerce_data():
    """Fixture providing sample commerce data for successful responses."""
    return {
        "merchant_id": "10203040",
        "business_name": "TecnoNova Solutions",
        "status": "ACTIVE",
        "is_active": True,
        "registration_date": "2022-07-19T15:45:00.501Z",
        "contact_info": {
            "email": "contact@tecnonova.com",
            "phone": "+573115246996"
        },
        "additional_info": {
            "document_number": "1020123455",
            "economic_activity": "4530",
            "establishment_info": {
                "type": "MAIN_OFFICE",
                "address": "Cra 20 No. 33 - 15, BOGOTA"
            }
        },
        "response_timestamp": datetime.utcnow().isoformat() + 'Z'
    }


@pytest.fixture
def api_gateway_event():
    """Fixture providing a sample API Gateway event."""
    return {
        "pathParameters": {
            "merchantId": "10203040"
        },
        "queryStringParameters": {
            "includeRawData": "true"
        },
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "test-client/1.0"
        },
        "httpMethod": "GET",
        "requestContext": {
            "requestId": "test-api-request-123",
            "stage": "test",
            "identity": {
                "sourceIp": "192.168.1.1"
            }
        }
    }


@pytest.fixture
def direct_invocation_event():
    """Fixture providing a sample direct invocation event."""
    return {
        "MerchantID": "10203040",
        "includeRawData": False
    }


@pytest.fixture
def mock_aws_services():
    """Fixture that mocks AWS services for testing."""
    with patch('src.services.aws_service.boto3') as mock_boto3:
        # Mock Secrets Manager client
        mock_secrets_client = Mock()
        mock_secrets_client.get_secret_value.return_value = {
            'SecretString': '{"redeban_crt": "mock_cert_data", "redeban_key": "mock_key_data"}'
        }

        # Mock DynamoDB resource and table
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'id': 'token',
                'access_token': 'mock_valid_token_123',
                'expires_in': 3600,
                'fecha_guardado': datetime.utcnow().isoformat()
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        # Mock Lambda client
        mock_lambda_client = Mock()
        mock_lambda_client.invoke.return_value = {
            'StatusCode': 200,
            'Payload': Mock()
        }

        # Configure boto3 client/resource creation
        def mock_client(service, **kwargs):
            if service == 'secretsmanager':
                return mock_secrets_client
            elif service == 'lambda':
                return mock_lambda_client
            return Mock()

        def mock_resource(service, **kwargs):
            if service == 'dynamodb':
                return mock_dynamodb
            return Mock()

        mock_boto3.client.side_effect = mock_client
        mock_boto3.resource.side_effect = mock_resource

        yield {
            'secrets_client': mock_secrets_client,
            'dynamodb': mock_dynamodb,
            'table': mock_table,
            'lambda_client': mock_lambda_client
        }


@pytest.fixture
def mock_file_operations():
    """Fixture that mocks file operations for certificate handling."""
    with patch('builtins.open', create=True) as mock_open, \
            patch('os.chmod') as mock_chmod, \
            patch('os.path.exists') as mock_exists, \
            patch('os.path.getsize') as mock_getsize:
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        yield {
            'open': mock_open,
            'chmod': mock_chmod,
            'exists': mock_exists,
            'getsize': mock_getsize,
            'file': mock_file
        }


@pytest.fixture
def mock_redeban_api():
    """Fixture that mocks Redeban API responses."""
    with patch('src.services.redeban_service.requests') as mock_requests:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "NameEnterprise": "TecnoNova Solutions",
            "DocumentType": "CC",
            "DocumentNumber": "1020123455",
            "Commerce": {
                "MerchantID": "10203040",
                "NameCommerce": "InnovaTech",
                "StatusCode": "1",
                "StatusDescription": "Activo"
            }
        }
        mock_response.elapsed.total_seconds.return_value = 0.5

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        mock_requests.Session.return_value = mock_session

        yield mock_session


class TestHelpers:
    """Helper utilities for testing."""

    @staticmethod
    def create_error_response_mock(status_code: int, message: str):
        """Create a mock error response."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.json.return_value = {"error": message}
        mock_response.text = f"Error: {message}"
        return mock_response

    @staticmethod
    def assert_response_structure(response: dict, expected_status: int):
        """Assert that response has correct structure."""
        assert 'statusCode' in response
        assert 'headers' in response
        assert 'body' in response
        assert response['statusCode'] == expected_status

        # Verify headers
        headers = response['headers']
        assert 'Content-Type' in headers
        assert headers['Content-Type'] == 'application/json'
        assert 'Access-Control-Allow-Origin' in headers

        # Verify body is valid JSON
        import json
        body = json.loads(response['body'])
        assert 'success' in body
        assert 'metadata' in body

        return body

    @staticmethod
    def assert_error_response(response: dict, expected_status: int, expected_message: str = None):
        """Assert that response is a proper error response."""
        body = TestHelpers.assert_response_structure(response, expected_status)

        assert body['success'] is False
        assert 'error' in body

        error = body['error']
        assert 'type' in error
        assert 'message' in error
        assert 'code' in error
        assert error['code'] == expected_status

        if expected_message:
            assert expected_message.lower() in error['message'].lower()

        return body

    @staticmethod
    def assert_success_response(response: dict, expected_data: dict = None):
        """Assert that response is a proper success response."""
        body = TestHelpers.assert_response_structure(response, 200)

        assert body['success'] is True
        assert 'data' in body

        if expected_data:
            for key, value in expected_data.items():
                assert key in body['data']
                assert body['data'][key] == value

        return body