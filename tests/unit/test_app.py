import json
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Agregar src al path para poder importar
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Configurar variables de entorno antes de importar
os.environ.update({
    'AWS_REGION': 'us-east-1',
    'DYNAMODB_TABLE': 'RedebanTokens-test',
    'SECRET_NAME': 'Redeban_Obtener_Token',
    'LOG_LEVEL': 'INFO'
})

from src.app import lambda_handler, extract_merchant_id, validate_merchant_id


class MockContext:
    """Mock del contexto de AWS Lambda"""

    def __init__(self):
        self.aws_request_id = "test-request-123"
        self.function_name = "test-function"
        self.memory_limit_in_mb = 1024


class TestExtractMerchantId:
    """Tests para la función extract_merchant_id"""

    def test_extract_from_path_parameters(self):
        """Test extraer merchant_id desde pathParameters (API Gateway)"""
        event = {
            "pathParameters": {
                "merchantId": "12345678"
            }
        }

        result = extract_merchant_id(event)
        assert result == "12345678"

    def test_extract_from_path_parameters_with_spaces(self):
        """Test extraer merchant_id con espacios que se deben limpiar"""
        event = {
            "pathParameters": {
                "merchantId": "  12345678  "
            }
        }

        result = extract_merchant_id(event)
        assert result == "12345678"

    def test_extract_from_direct_invocation(self):
        """Test extraer merchant_id desde invocación directa"""
        event = {
            "MerchantID": "87654321"
        }

        result = extract_merchant_id(event)
        assert result == "87654321"

    def test_extract_from_body(self):
        """Test extraer merchant_id desde body de request"""
        event = {
            "body": json.dumps({"MerchantID": "11223344"})
        }

        result = extract_merchant_id(event)
        assert result == "11223344"

    def test_extract_from_body_invalid_json(self):
        """Test con body que no es JSON válido"""
        event = {
            "body": "invalid json"
        }

        result = extract_merchant_id(event)
        assert result == "10203040"  # Default value

    def test_extract_default_value(self):
        """Test valor por defecto cuando no se encuentra merchant_id"""
        event = {}

        result = extract_merchant_id(event)
        assert result == "10203040"

    def test_extract_with_numeric_merchant_id(self):
        """Test con merchant_id numérico que se debe convertir a string"""
        event = {
            "MerchantID": 12345678
        }

        result = extract_merchant_id(event)
        assert result == "12345678"


class TestValidateMerchantId:
    """Tests para la función validate_merchant_id"""

    def test_valid_merchant_id(self):
        """Test con merchant_id válido"""
        assert validate_merchant_id("12345678") is True

    def test_invalid_empty(self):
        """Test con merchant_id vacío"""
        assert validate_merchant_id("") is False
        assert validate_merchant_id(None) is False

    def test_invalid_length_short(self):
        """Test con merchant_id muy corto"""
        assert validate_merchant_id("123") is False

    def test_invalid_length_long(self):
        """Test con merchant_id muy largo"""
        assert validate_merchant_id("123456789") is False

    def test_invalid_non_numeric(self):
        """Test con merchant_id no numérico"""
        assert validate_merchant_id("abcd1234") is False
        assert validate_merchant_id("1234abcd") is False

    def test_valid_with_spaces(self):
        """Test con merchant_id válido con espacios (se deben limpiar)"""
        assert validate_merchant_id("  12345678  ") is True


class TestLambdaHandler:
    """Tests para la función lambda_handler principal"""

    def setup_method(self):
        """Setup para cada test"""
        self.context = MockContext()

    @patch('src.app.aws_service')
    @patch('src.app.redeban_service')
    def test_successful_execution(self, mock_redeban, mock_aws):
        """Test ejecución exitosa completa"""
        # Configurar mocks
        mock_aws.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws.get_valid_token.return_value = "test_token_123"
        mock_redeban.get_commerce_info.return_value = {
            "merchant_id": "10203040",
            "business_name": "Test Business Corp",
            "status": "ACTIVE",
            "is_active": True,
            "contact_info": {"email": "test@business.com"}
        }

        # Evento de prueba
        event = {"MerchantID": "10203040"}

        # Ejecutar
        result = lambda_handler(event, self.context)

        # Verificaciones
        assert result['statusCode'] == 200

        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['data']['merchant_id'] == "10203040"
        assert body['data']['business_name'] == "Test Business Corp"
        assert 'timestamp' in body['metadata']

        # Verificar que se llamaron los métodos correctos
        mock_aws.get_certificates.assert_called_once()
        mock_aws.get_valid_token.assert_called_once()
        mock_redeban.get_commerce_info.assert_called_once()

    def test_invalid_merchant_id(self):
        """Test con merchant_id inválido"""
        event = {"MerchantID": "invalid123"}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['success'] is False
        assert 'dígitos numéricos' in body['error']['message']

    @patch('src.app.aws_service')
    def test_certificate_error(self, mock_aws):
        """Test error obteniendo certificados"""
        mock_aws.get_certificates.side_effect = Exception("Error obteniendo certificados")

        event = {"MerchantID": "10203040"}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['success'] is False
        assert 'certificados' in body['error']['message']

    @patch('src.app.aws_service')
    def test_token_error(self, mock_aws):
        """Test error obteniendo token"""
        mock_aws.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws.get_valid_token.side_effect = Exception("Token inválido o expirado")

        event = {"MerchantID": "10203040"}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 401
        body = json.loads(result['body'])
        assert body['success'] is False

    @patch('src.app.aws_service')
    @patch('src.app.redeban_service')
    def test_commerce_not_found(self, mock_redeban, mock_aws):
        """Test comercio no encontrado"""
        mock_aws.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws.get_valid_token.return_value = "test_token_123"
        mock_redeban.get_commerce_info.side_effect = Exception("Comercio no encontrado: 99999999")

        event = {"MerchantID": "99999999"}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 404
        body = json.loads(result['body'])
        assert body['success'] is False
        assert 'no encontrado' in body['error']['message']

    @patch('src.app.aws_service')
    @patch('src.app.redeban_service')
    def test_access_forbidden(self, mock_redeban, mock_aws):
        """Test acceso prohibido"""
        mock_aws.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws.get_valid_token.return_value = "test_token_123"
        mock_redeban.get_commerce_info.side_effect = Exception("Acceso prohibido - permisos insuficientes")

        event = {"MerchantID": "10203040"}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 403
        body = json.loads(result['body'])
        assert body['success'] is False

    def test_response_headers(self):
        """Test que las respuestas tengan los headers correctos"""
        event = {"MerchantID": "invalid"}

        result = lambda_handler(event, self.context)

        headers = result['headers']
        assert headers['Content-Type'] == 'application/json'
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'X-Response-ID' in headers
        assert 'Cache-Control' in headers

    @patch('src.app.aws_service')
    @patch('src.app.redeban_service')
    def test_api_gateway_event(self, mock_redeban, mock_aws):
        """Test con evento desde API Gateway"""
        # Configurar mocks
        mock_aws.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws.get_valid_token.return_value = "test_token_123"
        mock_redeban.get_commerce_info.return_value = {
            "merchant_id": "12345678",
            "business_name": "API Gateway Test",
            "status": "ACTIVE",
            "is_active": True
        }

        # Evento de API Gateway
        event = {
            "pathParameters": {
                "merchantId": "12345678"
            },
            "queryStringParameters": {
                "includeRawData": "true"
            },
            "httpMethod": "GET",
            "headers": {
                "Content-Type": "application/json"
            },
            "requestContext": {
                "requestId": "api-gateway-test-123"
            }
        }

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['data']['merchant_id'] == "12345678"


class TestErrorHandling:
    """Tests específicos para manejo de errores"""

    def setup_method(self):
        self.context = MockContext()

    @patch('src.app.aws_service')
    def test_unexpected_exception(self, mock_aws):
        """Test excepción inesperada"""
        mock_aws.get_certificates.side_effect = RuntimeError("Error inesperado")

        event = {"MerchantID": "10203040"}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['success'] is False
        assert body['error']['type'] == 'INTERNAL_SERVER_ERROR'

    def test_value_error_handling(self):
        """Test manejo de ValueError (errores de validación)"""
        # Este test usa un merchant_id que causará ValueError
        event = {"MerchantID": ""}

        result = lambda_handler(event, self.context)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['success'] is False
        assert body['error']['type'] == 'VALIDATION_ERROR'


class TestResponseFormat:
    """Tests para validar el formato de respuestas"""

    def setup_method(self):
        self.context = MockContext()

    @patch('src.app.aws_service')
    @patch('src.app.redeban_service')
    def test_success_response_format(self, mock_redeban, mock_aws):
        """Test formato de respuesta exitosa"""
        mock_aws.get_certificates.return_value = ("/tmp/cert.crt", "/tmp/key.key")
        mock_aws.get_valid_token.return_value = "test_token"
        mock_redeban.get_commerce_info.return_value = {
            "merchant_id": "10203040",
            "business_name": "Test Business",
            "status": "ACTIVE"
        }

        event = {"MerchantID": "10203040"}
        result = lambda_handler(event, self.context)

        # Verificar estructura de respuesta
        assert 'statusCode' in result
        assert 'headers' in result
        assert 'body' in result

        body = json.loads(result['body'])
        assert 'success' in body
        assert 'data' in body
        assert 'metadata' in body

        metadata = body['metadata']
        assert 'timestamp' in metadata
        assert 'response_id' in metadata
        assert 'version' in metadata

    def test_error_response_format(self):
        """Test formato de respuesta de error"""
        event = {"MerchantID": "invalid"}
        result = lambda_handler(event, self.context)

        body = json.loads(result['body'])
        assert 'success' in body
        assert body['success'] is False
        assert 'error' in body
        assert 'metadata' in body

        error = body['error']
        assert 'type' in error
        assert 'message' in error
        assert 'code' in error


# Fixtures para tests
@pytest.fixture
def sample_commerce_data():
    """Fixture con datos de comercio de ejemplo"""
    return {
        "merchant_id": "10203040",
        "business_name": "Test Business Corporation",
        "status": "ACTIVE",
        "is_active": True,
        "registration_date": "2023-01-15T10:30:00Z",
        "contact_info": {
            "email": "contact@testbusiness.com",
            "phone": "+1234567890"
        },
        "response_timestamp": "2024-01-15T10:30:00Z"
    }


@pytest.fixture
def api_gateway_event():
    """Fixture con evento de API Gateway"""
    return {
        "pathParameters": {
            "merchantId": "10203040"
        },
        "queryStringParameters": {
            "includeRawData": "false"
        },
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        "httpMethod": "GET",
        "requestContext": {
            "requestId": "test-api-gateway-123",
            "stage": "test"
        }
    }


@pytest.fixture
def direct_invocation_event():
    """Fixture con evento de invocación directa"""
    return {
        "MerchantID": "10203040",
        "includeRawData": True
    }