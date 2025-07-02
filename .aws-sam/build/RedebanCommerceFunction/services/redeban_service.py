    import requests
    import os
    import time
    from datetime import datetime
    from src.utils import logger
    logger = logger.setup_logger()


    class RedebanService:
        """
        Clase que maneja la comunicación con la API de Redeban KYC
        Implementa patrones de retry, timeout y manejo de errores específicos
        """

        def __init__(self):
            """Inicializa el servicio con configuración"""
            # Configuración desde variables de entorno
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

            # Configurar sesión de requests para reutilizar conexiones
            self.session = requests.Session()

            # Headers base que se usan en todas las peticiones
            self.session.headers.update({
                'User-Agent': 'RedebanKYC-Lambda/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })

            logger.info(f"RedebanService inicializado - URL: {self.base_url}{self.api_path}")

        def get_commerce_info(self, merchant_id, token, cert_path, key_path, include_raw_data=True):
            """
            Consulta información del comercio en la API de Redeban

            Args:
                merchant_id (str): ID del comercio a consultar
                token (str): Token de autenticación Bearer
                cert_path (str): Ruta al archivo de certificado
                key_path (str): Ruta al archivo de llave privada
                include_raw_data (bool): Si incluir datos raw en la respuesta

            Returns:
                dict: Información procesada del comercio

            Raises:
                Exception: Si hay errores en la consulta
            """
            # URL completa para consultar el comercio
            url = f"{self.base_url}{self.api_path}/enterprise/Commerce/{merchant_id}"

            # Headers específicos para esta petición
            headers = {
                'Authorization': f'Bearer {token}'
            }

            logger.info(f"Consultando comercio {merchant_id} en Redeban API: {url}")

            # Implementar retry con backoff exponencial
            last_exception = None

            for attempt in range(self.max_retries):
                try:
                    # Calcular delay para retry (backoff exponencial)
                    if attempt > 0:
                        delay = min(2 ** attempt, 10)  # Máximo 10 segundos
                        logger.info(f"Reintentando en {delay} segundos... (intento {attempt + 1})")
                        time.sleep(delay)

                    logger.info(f"Realizando petición HTTP (intento {attempt + 1}/{self.max_retries})")

                    # Hacer la petición con certificados de cliente
                    response = self.session.get(
                        url,
                        headers=headers,
                        cert=(cert_path, key_path),  # Certificados de cliente para autenticación mutua
                        timeout=self.timeout,
                        verify=True  # Verificar certificados SSL del servidor
                    )

                    # Manejar diferentes códigos de respuesta
                    return self._handle_response(response, merchant_id, include_raw_data)

                except requests.exceptions.HTTPError as e:
                    # Errores HTTP específicos
                    last_exception = e
                    status_code = e.response.status_code if e.response else 0

                    logger.warning(f"Error HTTP {status_code} en intento {attempt + 1}: {str(e)}")

                    # Algunos errores no se deben reintentar
                    if status_code in [400, 401, 403, 404]:
                        break  # No reintentar errores de cliente

                    # Para 5xx y otros errores, continuar con retry

                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    logger.warning(f"Error de conexión en intento {attempt + 1}: {str(e)}")

                except requests.exceptions.Timeout as e:
                    last_exception = e
                    logger.warning(f"Timeout en intento {attempt + 1}: {str(e)}")

                except requests.exceptions.RequestException as e:
                    last_exception = e
                    logger.warning(f"Error de request en intento {attempt + 1}: {str(e)}")

                except Exception as e:
                    last_exception = e
                    logger.error(f"Error inesperado en intento {attempt + 1}: {str(e)}")

            # Si llegamos aquí, todos los intentos fallaron
            logger.error(f"Todos los intentos fallaron para merchant_id: {merchant_id}")
            self._raise_final_exception(last_exception)

        def _handle_response(self, response, merchant_id, include_raw_data):
            """
            Maneja la respuesta HTTP y extrae la información

            Args:
                response: Objeto Response de requests
                merchant_id (str): ID del comercio consultado
                include_raw_data (bool): Si incluir datos raw

            Returns:
                dict: Datos procesados del comercio
            """
            status_code = response.status_code

            logger.info(
                f"Respuesta recibida - Status: {status_code}, Content-Type: {response.headers.get('content-type', 'unknown')}")

            # Manejar diferentes códigos de estado
            if status_code == 200:
                # Respuesta exitosa
                try:
                    raw_data = response.json()
                    logger.info(f"Respuesta exitosa para comercio {merchant_id}")
                    return self._process_commerce_data(raw_data, merchant_id, include_raw_data)

                except ValueError as e:
                    logger.error(f"Error parseando JSON de respuesta: {str(e)}")
                    logger.error(f"Contenido de respuesta: {response.text[:500]}...")
                    raise Exception(f"Respuesta de API no es JSON válido: {str(e)}")

            elif status_code == 404:
                logger.warning(f"Comercio no encontrado: {merchant_id}")
                raise Exception(f"Comercio no encontrado: {merchant_id}")

            elif status_code == 401:
                logger.error("Token de autenticación inválido o expirado")
                raise Exception("Token de autenticación inválido")

            elif status_code == 403:
                logger.error("Acceso prohibido - permisos insuficientes")
                raise Exception("Acceso prohibido - permisos insuficientes")

            elif status_code == 429:
                logger.error("Límite de rate limiting excedido")
                raise Exception("Límite de peticiones excedido, intente más tarde")

            elif 500 <= status_code < 600:
                # Error del servidor
                error_msg = f"Error del servidor Redeban: {status_code}"
                try:
                    error_details = response.text
                    if error_details:
                        error_msg += f" - {error_details[:200]}"
                except:
                    pass

                logger.error(error_msg)
                raise requests.exceptions.HTTPError(error_msg, response=response)

            else:
                # Código de estado inesperado
                error_msg = f"Código de estado inesperado: {status_code}"
                logger.error(f"{error_msg} - {response.text[:200]}")
                raise requests.exceptions.HTTPError(error_msg, response=response)

        def _process_commerce_data(self, raw_data, merchant_id, include_raw_data):
            """
            Procesa los datos del comercio recibidos de la API

            Args:
                raw_data (dict): Datos raw de la API
                merchant_id (str): ID del comercio
                include_raw_data (bool): Si incluir datos raw en respuesta

            Returns:
                dict: Datos procesados y estructurados
            """
            try:
                logger.info(f"Procesando datos del comercio {merchant_id}")

                # Extraer información relevante con valores por defecto
                processed_data = {
                    'merchant_id': merchant_id,
                    'business_name': raw_data.get('businessName', 'N/A'),
                    'status': raw_data.get('status', 'UNKNOWN'),
                    'registration_date': self._parse_date(raw_data.get('registrationDate')),
                    'contact_info': raw_data.get('contactInfo', {}),
                    'is_active': raw_data.get('status', '').upper() == 'ACTIVE',
                    'response_timestamp': datetime.utcnow().isoformat() + 'Z'
                }

                # Agregar información adicional si está disponible
                if 'documentNumber' in raw_data:
                    processed_data['document_number'] = raw_data['documentNumber']

                if 'establishmentInfo' in raw_data:
                    processed_data['establishment_info'] = raw_data['establishmentInfo']

                if 'economicActivity' in raw_data:
                    processed_data['economic_activity'] = raw_data['economicActivity']

                # Incluir datos raw si se solicita
                if include_raw_data:
                    processed_data['raw_data'] = raw_data

                # Log de información extraída
                logger.info(
                    f"Comercio procesado - Nombre: {processed_data['business_name']}, Status: {processed_data['status']}")

                return processed_data

            except Exception as e:
                logger.error(f"Error procesando datos del comercio: {str(e)}")
                logger.error(f"Datos raw recibidos: {str(raw_data)[:500]}...")
                raise Exception(f"Error procesando respuesta de la API: {str(e)}")

        def _parse_date(self, date_str):
            """
            Parsea fecha desde string a formato ISO

            Args:
                date_str (str): String de fecha a parsear

            Returns:
                str or None: Fecha en formato ISO o None si no se puede parsear
            """
            if not date_str:
                return None

            try:
                # Intentar diferentes formatos de fecha
                date_formats = [
                    '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO con microsegundos
                    '%Y-%m-%dT%H:%M:%SZ',  # ISO básico
                    '%Y-%m-%d %H:%M:%S',  # Formato SQL
                    '%Y-%m-%d',  # Solo fecha
                    '%d/%m/%Y',  # Formato colombiano
                    '%m/%d/%Y'  # Formato americano
                ]

                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt)
                        return parsed_date.isoformat() + 'Z'
                    except ValueError:
                        continue

                # Si no se puede parsear, retornar el string original
                logger.warning(f"No se pudo parsear la fecha: {date_str}")
                return date_str

            except Exception as e:
                logger.warning(f"Error parseando fecha {date_str}: {str(e)}")
                return date_str

        def _raise_final_exception(self, last_exception):
            """
            Lanza la excepción final después de agotar todos los reintentos

            Args:
                last_exception: La última excepción capturada
            """
            if isinstance(last_exception, requests.exceptions.HTTPError):
                if hasattr(last_exception, 'response') and last_exception.response:
                    status_code = last_exception.response.status_code
                    if status_code == 404:
                        raise Exception("Comercio no encontrado después de múltiples intentos")
                    elif status_code == 401:
                        raise Exception("Token de autenticación inválido")
                    elif status_code == 403:
                        raise Exception("Acceso prohibido - permisos insuficientes")
                    elif status_code >= 500:
                        raise Exception("Error del servidor Redeban - servicio no disponible")

                raise Exception(f"Error HTTP: {str(last_exception)}")

            elif isinstance(last_exception, requests.exceptions.ConnectionError):
                raise Exception("Error de conexión con la API de Redeban - servicio no disponible")

            elif isinstance(last_exception, requests.exceptions.Timeout):
                raise Exception("Timeout consultando la API de Redeban - servicio demorado")

            elif isinstance(last_exception, requests.exceptions.RequestException):
                raise Exception(f"Error de red consultando Redeban: {str(last_exception)}")

            else:
                raise Exception(f"Error inesperado consultando API de Redeban: {str(last_exception)}")

        def health_check(self):
            """
            Realiza un health check básico de la API de Redeban

            Returns:
                dict: Estado del servicio
            """
            try:
                # URL base para health check
                health_url = f"{self.base_url}/health"

                response = self.session.get(
                    health_url,
                    timeout=10,
                    verify=True
                )

                return {
                    'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                    'status_code': response.status_code,
                    'response_time_ms': response.elapsed.total_seconds() * 1000
                }

            except Exception as e:
                return {
                    'status': 'unhealthy',
                    'error': str(e)
                }