import requests
import os
import uuid
from datetime import datetime
from utils.logger import setup_logger

logger = setup_logger()


class RedebanService:

    def __init__(self):
        self.base_url = os.getenv(
            'REDEBAN_BASE_URL',
            'https://api.qa.sandboxhubredeban.com:9445'
        )
        self.api_path = os.getenv(
            'REDEBAN_API_PATH',
            '/rbmcalidad/calidad/api/kyc/v3.0.0/enterprise'
        )
        self.timeout = int(os.getenv('REDEBAN_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('REDEBAN_MAX_RETRIES', '3'))

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'RedebanKYC-Lambda/1.0',
            'Cache-Control': 'no-cache'
        })

        logger.info(f"RedebanService inicializado - URL: {self.base_url}{self.api_path}")

    def get_commerce_info(self, merchant_id, token, cert_path, key_path, include_raw_data=True, extra_params=None):
        """
        Consulta información del comercio usando el endpoint correcto de la API Redeban.
        Solo usa el método GET a /Commerce/{merchant_id}
        Permite agregar parámetros adicionales si la API lo requiere.
        """
        # Validaciones
        if not merchant_id or not str(merchant_id).strip():
            raise ValueError("merchant_id es requerido y no puede estar vacío")
        if not token or not str(token).strip():
            raise ValueError("El token de autenticación es requerido y no puede estar vacío")

        url = f"{self.base_url}{self.api_path}/Commerce/{merchant_id}"

        # Fecha actual en formato ISO 8601 con milisegundos
        now_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]

        # Headers obligatorios según Swagger
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'RedebanKYC-Lambda/1.0',
            'Cache-Control': 'no-cache',
            'Date': now_iso,
            'X-Forwarded-For': os.getenv('REDEBAN_X_FORWARDED_FOR', '127.0.0.1'),
            'RBMURI': os.getenv('REDEBAN_RBMURI', 'P2M'),
            'RBM-FROM': os.getenv('REDEBAN_RBM_FROM', '218f3105-811f-4713-9818-8c7031e43c01'),
            'Geolocation': os.getenv('REDEBAN_GEOLOCATION', '+00.0000-000.0000'),
            'X-Request-ID': str(uuid.uuid4()),
            'Origin': os.getenv('REDEBAN_ORIGIN', 'app.mibanco.com:8080'),
        }
        device_fingerprint = os.getenv('REDEBAN_DEVICE_FINGERPRINT')
        if device_fingerprint:
            headers['X-Device-Fingerprint'] = device_fingerprint

        # Parámetros por defecto
        params = {}
        if include_raw_data is not None:
            params['format'] = 'json'
            params['include_details'] = 'true' if include_raw_data else 'false'

        # Agrega parámetros extra si se requieren (por ejemplo, channel, productType)
        if extra_params and isinstance(extra_params, dict):
            params.update(extra_params)

        logger.info(f"GET a {url} con params {params}")

        response = self.session.get(
            url,
            headers=headers,
            params=params,
            cert=(cert_path, key_path),
            timeout=self.timeout,
            verify=False
        )

        return self._handle_response(response, merchant_id, include_raw_data)

    def _handle_response(self, response, merchant_id, include_raw_data):
        """
        Maneja la respuesta HTTP con mejor logging
        """
        status_code = response.status_code

        logger.info(f"Respuesta recibida:")
        logger.info(f"  Status: {status_code}")
        logger.info(f"  Headers: {dict(response.headers)}")
        logger.info(f"  URL: {response.url}")

        try:
            content_preview = response.text[:1000] if response.text else "Sin contenido"
            logger.info(f"  Content preview: {content_preview}")
        except:
            logger.info("  Content: No disponible")

        if status_code == 200:
            try:
                raw_data = response.json()
                logger.info(f"✅ Respuesta exitosa para comercio {merchant_id}")
                return self._process_commerce_data(raw_data, merchant_id, include_raw_data)
            except ValueError as e:
                logger.error(f"Error parseando JSON: {str(e)}")
                raise Exception(f"Respuesta no es JSON válido: {str(e)}")

        elif status_code == 400:
            try:
                error_data = response.json()
                error_msg = error_data.get('moreInformation',
                           error_data.get('message',
                           error_data.get('error', 'Bad Request')))
                logger.error(f"Error 400 detallado: {error_data}")
                raise Exception(f"Parámetros API incorrectos: {error_msg}")
            except ValueError:
                error_text = response.text[:200] if response.text else "Sin detalles"
                logger.error(f"Error 400 (no JSON): {error_text}")
                raise Exception(f"Bad Request: {error_text}")

        elif status_code == 401:
            logger.error("Token de autenticación inválido")
            raise Exception("Token de autenticación inválido o expirado")

        elif status_code == 403:
            logger.error("Acceso prohibido")
            raise Exception("Acceso prohibido - verificar permisos de API")

        elif status_code == 404:
            logger.error(f"Comercio no encontrado: {merchant_id}")
            raise Exception(f"Comercio no encontrado: {merchant_id}")

        elif status_code == 422:
            try:
                error_data = response.json()
                logger.error(f"Error de validación: {error_data}")
                raise Exception(f"Datos de entrada inválidos: {error_data.get('message', 'Error de validación')}")
            except ValueError:
                raise Exception("Error de validación de datos")

        elif status_code == 429:
            logger.error("Rate limit excedido")
            raise Exception("Límite de peticiones excedido")

        elif 500 <= status_code < 600:
            logger.error(f"Error del servidor: {status_code}")
            raise Exception(f"Error del servidor Redeban: {status_code}")

        else:
            logger.error(f"Código de estado inesperado: {status_code}")
            raise Exception(f"Código de estado inesperado: {status_code}")

    def _process_commerce_data(self, raw_data, merchant_id, include_raw_data):
        """
        Procesa los datos del comercio con manejo robusto
        """
        try:
            logger.info(f"Procesando datos del comercio {merchant_id}")
            logger.info(f"Estructura de datos recibida: {list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data)}")

            processed_data = {
                'merchant_id': merchant_id,
                'response_timestamp': datetime.utcnow().isoformat() + 'Z'
            }

            if isinstance(raw_data, dict):
                if 'businessName' in raw_data or 'merchant_id' in raw_data:
                    processed_data.update({
                        'business_name': raw_data.get('businessName', raw_data.get('name', 'N/A')),
                        'status': raw_data.get('status', 'UNKNOWN'),
                        'is_active': self._determine_active_status(raw_data),
                        'registration_date': self._parse_date(raw_data.get('registrationDate')),
                        'contact_info': raw_data.get('contactInfo', {})
                    })
                elif 'commerce' in raw_data:
                    commerce_data = raw_data['commerce']
                    processed_data.update({
                        'business_name': commerce_data.get('businessName', commerce_data.get('name', 'N/A')),
                        'status': commerce_data.get('status', 'UNKNOWN'),
                        'is_active': self._determine_active_status(commerce_data),
                        'registration_date': self._parse_date(commerce_data.get('registrationDate')),
                        'contact_info': commerce_data.get('contactInfo', {})
                    })
                elif 'transaction' in raw_data or 'application' in raw_data:
                    commerce_info = {}
                    if 'commerce' in raw_data:
                        commerce_info = raw_data['commerce']
                    elif 'merchant' in raw_data:
                        commerce_info = raw_data['merchant']

                    processed_data.update({
                        'business_name': commerce_info.get('merchant_id', merchant_id),
                        'status': 'ACTIVE',
                        'is_active': True,
                        'registration_date': None,
                        'contact_info': {}
                    })
                else:
                    logger.warning(f"Estructura de respuesta no reconocida: {raw_data.keys()}")
                    processed_data.update({
                        'business_name': str(raw_data.get('name', raw_data.get('id', 'Información no disponible'))),
                        'status': 'UNKNOWN',
                        'is_active': False,
                        'registration_date': None,
                        'contact_info': {}
                    })

                additional_fields = ['documentNumber', 'establishmentInfo', 'economicActivity', 'address']
                for field in additional_fields:
                    if field in raw_data:
                        processed_data[self._snake_case(field)] = raw_data[field]

                if include_raw_data:
                    processed_data['raw_data'] = raw_data

            else:
                processed_data.update({
                    'business_name': f'Comercio {merchant_id}',
                    'status': 'UNKNOWN',
                    'is_active': False,
                    'registration_date': None,
                    'contact_info': {},
                    'raw_data': raw_data if include_raw_data else None
                })

            logger.info(f"Comercio procesado: {processed_data.get('business_name')} - {processed_data.get('status')}")
            return processed_data

        except Exception as e:
            logger.error(f"Error procesando datos del comercio: {str(e)}")
            return {
                'merchant_id': merchant_id,
                'business_name': f'Comercio {merchant_id}',
                'status': 'PROCESSING_ERROR',
                'is_active': False,
                'registration_date': None,
                'contact_info': {},
                'response_timestamp': datetime.utcnow().isoformat() + 'Z',
                'raw_data': raw_data if include_raw_data else None,
                'processing_error': str(e)
            }

    def _determine_active_status(self, data):
        """
        Determina si el comercio está activo basado en varios campos posibles
        """
        if not isinstance(data, dict):
            return False

        if 'active' in data:
            return bool(data['active'])
        if 'isActive' in data:
            return bool(data['isActive'])

        status = str(data.get('status', '')).upper()
        active_statuses = ['ACTIVE', 'ACTIVO', 'ENABLED', 'HABILITADO', 'APPROVED', 'SUCCESS']
        if status in active_statuses:
            return True

        inactive_statuses = ['INACTIVE', 'INACTIVO', 'DISABLED', 'DESHABILITADO', 'CANCELLED', 'SUSPENDED']
        if status in inactive_statuses:
            return False

        if data.get('merchant_id') or data.get('merchantId'):
            return True

        return False

    def _parse_date(self, date_str):
        """
        Parsea fecha con múltiples formatos
        """
        if not date_str:
            return None

        try:
            date_formats = [
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%d/%m/%Y',
                '%m/%d/%Y',
                '%d-%m-%Y'
            ]

            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(str(date_str), fmt)
                    return parsed_date.isoformat() + 'Z'
                except ValueError:
                    continue

            return str(date_str)

        except Exception as e:
            logger.warning(f"Error parseando fecha {date_str}: {str(e)}")
            return str(date_str) if date_str else None

    def _snake_case(self, camel_str):
        """
        Convierte camelCase a snake_case
        """
        import re
        s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', camel_str)
        return s1.lower()

    def health_check(self):
        """
        Health check básico de la API
        """
        try:
            health_url = f"{self.base_url}/health"
            response = self.session.get(health_url, timeout=10, verify=False)
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'status_code': response.status_code,
                'response_time_ms': response.elapsed.total_seconds() * 1000
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def test_connectivity(self, token, cert_path, key_path):
        """
        Método para probar conectividad con diferentes enfoques
        """
        test_results = []

        # Test 1: Endpoint base
        try:
            url = f"{self.base_url}{self.api_path}"
            response = self.session.get(url, timeout=10, verify=False)
            test_results.append({
                'test': 'Base endpoint',
                'status': response.status_code,
                'success': response.status_code < 500
            })
        except Exception as e:
            test_results.append({
                'test': 'Base endpoint',
                'error': str(e),
                'success': False
            })

        # Test 2: Con certificados
        try:
            url = f"{self.base_url}{self.api_path}/Commerce/test"
            headers = {'Authorization': f'Bearer {token}'}
            response = self.session.get(
                url,
                headers=headers,
                cert=(cert_path, key_path),
                timeout=10,
                verify=False
            )
            test_results.append({
                'test': 'With certificates',
                'status': response.status_code,
                'success': response.status_code != 400  # 400 es error de parámetros, no de conectividad
            })
        except Exception as e:
            test_results.append({
                'test': 'With certificates',
                'error': str(e),
                'success': False
            })

        return test_results