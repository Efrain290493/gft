import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.redeban_service import RedebanService

class MockResponse:
    def __init__(self, status_code, json_data=None, text="", headers=None, url="mock://url"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}
        self.url = url
        self.elapsed = MagicMock(total_seconds=lambda: 0.1)
    def json(self):
        if self._json_data is not None:
            return self._json_data
        raise ValueError("No JSON")

def test_redeban_service_init():
    service = RedebanService()
    assert service.base_url
    assert service.api_path

def test_build_request_headers(monkeypatch):
    service = RedebanService()
    headers = {
        "Authorization": "Bearer token123",
        "Content-Type": "application/json",
        "Date": "2024-07-03T20:05:24.023",
        "X-Forwarded-For": "127.0.0.1",
        "RBMURI": "P2M",
        "RBM-FROM": "218f3105-811f-4713-9818-8c7031e43c01",
        "Geolocation": "+00.0000-000.0000",
        "X-Request-ID": "uuid",
        "Origin": "app.mibanco.com:8080"
    }
    # Simula _build_request_headers si existe, si no, prueba get_commerce_info headers
    if hasattr(service, "_build_request_headers"):
        built_headers = service._build_request_headers("token123")
        for k in headers:
            assert k in built_headers
    else:
        # Si no existe, prueba get_commerce_info y monkeypatch requests.Session.get
        monkeypatch.setattr(service.session, "get", lambda *a, **kw: MockResponse(200, {"merchant_id": "10203040"}))
        result = service.get_commerce_info("10203040", "token123", "/tmp/cert", "/tmp/key")
        assert "merchant_id" in result

def test_handle_response_success(monkeypatch):
    service = RedebanService()
    mock_json = {
        "businessName": "Test S.A.",
        "status": "ACTIVE",
        "registrationDate": "2024-01-31T20:05:24.023",
        "contactInfo": {"email": "test@test.com"}
    }
    response = MockResponse(200, mock_json)
    result = service._handle_response(response, "10203040", True)
    assert result["business_name"] == "Test S.A."
    assert result["is_active"] is True

@pytest.mark.parametrize("status_code,error_key,error_msg", [
    (400, "moreInformation", "Parámetros API incorrectos"),
    (401, None, "Token de autenticación inválido"),
    (403, None, "Acceso prohibido"),
    (404, None, "Comercio no encontrado"),
    (422, "message", "Datos de entrada inválidos"),
    (429, None, "Límite de peticiones excedido"),
    (500, None, "Error del servidor Redeban"),
])
def test_handle_response_errors(monkeypatch, status_code, error_key, error_msg):
    service = RedebanService()
    error_json = {error_key: "error detail"} if error_key else None
    response = MockResponse(status_code, error_json, text="error text")
    with pytest.raises(Exception) as exc:
        service._handle_response(response, "10203040", True)
    assert error_msg.split()[0] in str(exc.value)

def test_process_commerce_data_variants():
    service = RedebanService()
    # Caso 1: businessName directo
    data = {"businessName": "Comercio Uno", "status": "ACTIVE"}
    result = service._process_commerce_data(data, "10203040", False)
    assert result["business_name"] == "Comercio Uno"
    # Caso 2: campo commerce anidado
    data = {"commerce": {"businessName": "Comercio Dos", "status": "INACTIVE"}}
    result = service._process_commerce_data(data, "10203040", False)
    assert result["business_name"] == "Comercio Dos"
    # Caso 3: estructura desconocida
    data = {"foo": "bar"}
    result = service._process_commerce_data(data, "10203040", False)
    assert result["status"] == "UNKNOWN"
    # Caso 4: no dict
    result = service._process_commerce_data("no dict", "10203040", False)
    assert result["status"] == "UNKNOWN"

def test_parse_date_formats():
    service = RedebanService()
    assert service._parse_date("2024-01-31T20:05:24.023") is not None
    assert service._parse_date("31/01/2024") is not None
    assert service._parse_date(None) is None

def test_snake_case():
    service = RedebanService()
    assert service._snake_case("CamelCaseTest") == "camel_case_test"
    assert service._snake_case("already_snake") == "already_snake"