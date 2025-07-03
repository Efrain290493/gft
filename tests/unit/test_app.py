"""
Fixed unit tests for the main Lambda handler.

These tests properly mock all AWS services and external dependencies
to ensure predictable test outcomes and proper error code validation.

Author: DevSecOps Team
Version: 1.0.0
"""

import json
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
# Add tests to path for conftest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import (
    lambda_handler,
    _extract_merchant_id,
    _extract_include_raw_data,
    _validate_merchant_id,
    _determine_error_status_code,
    health_check_handler
)

# Import test helpers - FIXED IMPORT
from conftest import TestHelpers


class TestLambdaHandlerSuccess:
    """Test successful execution scenarios."""
    
    @patch('app.redeban_service')
    @patch('app.aws_service')
    def test_successful_merchant_lookup(self, mock_aws_service, mock_redeban_service, lambda_context, sample_commerce_data):
        """Test successful merchant lookup with all services working."""
        # Mock AWS service responses
        mock_aws_service.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws_service.get_valid_token.return_value = "valid_token_123"
        
        # Mock Redeban service response
        mock_redeban_service.get_commerce_info.return_value = sample_commerce_data
        
        # Test event
        event = {"MerchantID": "10203040"}
        
        # Execute
        response = lambda_handler(event, lambda_context)
        
        # Verify success response
        body = TestHelpers.assert_success_response(response, {
            "merchant_id": "10203040",
            "business_name": "TecnoNova Solutions"
        })
        
        # Verify service calls
        mock_aws_service.get_certificates.assert_called_once()
        mock_aws_service.get_valid_token.assert_called_once()
        mock_redeban_service.get_commerce_info.assert_called_once_with(
            merchant_id="10203040",
            token="valid_token_123",
            cert_path="/tmp/cert.crt",
            key_path="/tmp/key.key",
            include_raw_data=True
        )


class TestLambdaHandlerValidation:
    """Test input validation scenarios."""
    
    def test_invalid_merchant_id_format(self, lambda_context):
        """Test validation error for invalid merchant ID format."""
        event = {"MerchantID": "invalid123"}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 400, "numeric digits")
    
    def test_empty_merchant_id(self, lambda_context):
        """Test validation error for empty merchant ID."""
        event = {"MerchantID": ""}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 400, "numeric digits")


class TestLambdaHandlerErrorScenarios:
    """Test error handling scenarios with proper mocking."""
    
    @patch('app.redeban_service')
    @patch('app.aws_service')
    def test_merchant_not_found(self, mock_aws_service, mock_redeban_service, lambda_context):
        """Test error when merchant is not found."""
        # Mock successful AWS services but merchant not found
        mock_aws_service.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws_service.get_valid_token.return_value = "valid_token"
        mock_redeban_service.get_commerce_info.side_effect = Exception("Merchant not found: 99999999")
        
        event = {"MerchantID": "99999999"}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 404, "not found")
    
    @patch('app.redeban_service')
    @patch('app.aws_service')
    def test_unauthorized_access(self, mock_aws_service, mock_redeban_service, lambda_context):
        """Test unauthorized access error."""
        # Mock services
        mock_aws_service.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws_service.get_valid_token.return_value = "valid_token"
        mock_redeban_service.get_commerce_info.side_effect = Exception("Unauthorized access to resource")
        
        event = {"MerchantID": "10203040"}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 401, "unauthorized")
    
    @patch('app.redeban_service')
    @patch('app.aws_service')
    def test_forbidden_access(self, mock_aws_service, mock_redeban_service, lambda_context):
        """Test forbidden access error."""
        # Mock services
        mock_aws_service.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws_service.get_valid_token.return_value = "valid_token"
        mock_redeban_service.get_commerce_info.side_effect = Exception("Access forbidden - insufficient permissions")
        
        event = {"MerchantID": "10203040"}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 403, "forbidden")
    
    @patch('app.redeban_service')
    @patch('app.aws_service')
    def test_timeout_error(self, mock_aws_service, mock_redeban_service, lambda_context):
        """Test timeout error handling."""
        # Mock services
        mock_aws_service.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws_service.get_valid_token.return_value = "valid_token"
        mock_redeban_service.get_commerce_info.side_effect = Exception("Request timeout after 30 seconds")
        
        event = {"MerchantID": "10203040"}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 504, "timeout")
    
    @patch('app.redeban_service')
    @patch('app.aws_service')
    def test_service_unavailable(self, mock_aws_service, mock_redeban_service, lambda_context):
        """Test service unavailable error."""
        # Mock services
        mock_aws_service.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws_service.get_valid_token.return_value = "valid_token"
        mock_redeban_service.get_commerce_info.side_effect = Exception("Service unavailable - connection failed")
        
        event = {"MerchantID": "10203040"}
        
        response = lambda_handler(event, lambda_context)
        
        TestHelpers.assert_error_response(response, 503, "unavailable")


class TestMerchantIdExtraction:
    """Test merchant ID extraction from various event formats."""
    
    def test_extract_from_path_parameters(self):
        """Test extraction from API Gateway path parameters."""
        event = {"pathParameters": {"merchantId": "12345678"}}
        result = _extract_merchant_id(event)
        assert result == "12345678"
    
    def test_extract_from_direct_invocation(self):
        """Test extraction from direct Lambda invocation."""
        event = {"MerchantID": "87654321"}
        result = _extract_merchant_id(event)
        assert result == "87654321"
    
    def test_extract_default_fallback(self):
        """Test default fallback when no merchant ID found."""
        event = {"someOtherField": "value"}
        result = _extract_merchant_id(event)
        assert result == "10203040"


class TestMerchantIdValidation:
    """Test merchant ID validation logic."""
    
    def test_valid_merchant_ids(self):
        """Test validation of valid merchant IDs."""
        valid_ids = ["12345678", "00000000", "99999999", "10203040"]
        
        for merchant_id in valid_ids:
            assert _validate_merchant_id(merchant_id) is True
    
    def test_invalid_length(self):
        """Test validation of incorrect length."""
        invalid_lengths = ["1234567", "123456789", "123", "1234567890"]
        
        for merchant_id in invalid_lengths:
            assert _validate_merchant_id(merchant_id) is False
    
    def test_invalid_non_numeric(self):
        """Test validation of non-numeric values."""
        invalid_values = ["abcd1234", "1234abcd", "1234-567", "1234 567"]
        
        for merchant_id in invalid_values:
            assert _validate_merchant_id(merchant_id) is False


class TestErrorStatusCodeDetermination:
    """Test error status code determination logic."""
    
    def test_not_found_errors(self):
        """Test detection of not found errors."""
        messages = [
            "Merchant not found",
            "Resource no encontrado",
            "The item was not found"
        ]
        
        for message in messages:
            assert _determine_error_status_code(message) == 404
    
    def test_authentication_errors(self):
        """Test detection of authentication errors."""
        messages = [
            "Invalid token",
            "Authentication failed",
            "Unauthorized access"
        ]
        
        for message in messages:
            assert _determine_error_status_code(message) == 401
    
    def test_timeout_errors(self):
        """Test detection of timeout errors."""
        messages = [
            "Request timeout",
            "Connection timeout",
            "Timeout occurred"
        ]
        
        for message in messages:
            assert _determine_error_status_code(message) == 504


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([
        __file__,
        "-v",
        "--cov=src",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--cov-fail-under=85"
    ])