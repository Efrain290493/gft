import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.aws_service import AWSService

def test_aws_service_init():
    service = AWSService()
    assert service.region
    assert service.dynamodb_table
    assert service.secret_name
    assert service.token_lambda_name

def test_is_token_valid_true():
    service = AWSService()
    token_item = {
        "access_token": "abc",
        "expires_in": 3600,
        "fecha_guardado": "2025-07-03T02:06:43.711027"
    }
    assert isinstance(service._is_token_valid(token_item), bool)