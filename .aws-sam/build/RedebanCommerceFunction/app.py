import json
from services.aws_service import AWSService
from services.redeban_service import RedebanService
from models.responses import create_success_response, create_error_response
from utils.logger import setup_logger

logger = setup_logger()

# Inicializar servicios (fuera del handler para optimización)
aws_service = AWSService()
redeban_service = RedebanService()


def lambda_handler(event, context):
    """
    Función principal que maneja las peticiones a la Lambda
    """
    try:
        logger.info(f"Iniciando procesamiento. Request ID: {context.aws_request_id}")

        # 1. Extraer MerchantID del evento
        merchant_id = extract_merchant_id(event)
        logger.info(f"Procesando merchant_id: {merchant_id}")

        # Validar merchant_id
        if not validate_merchant_id(merchant_id):
            return create_error_response("MerchantID debe ser exactamente 8 dígitos numéricos", 400)

        # 2. Extraer parámetros adicionales
        include_raw_data = extract_include_raw_data(event)
        logger.info(f"Include raw data: {include_raw_data}")

        # 3. Obtener certificados desde Secrets Manager
        logger.info("Obteniendo certificados desde Secrets Manager")
        cert_path, key_path = aws_service.get_certificates()

        # 4. Obtener token válido
        logger.info("Obteniendo token de autenticación")
        token = aws_service.get_valid_token()
        logger.info(f"Token obtenido (primeros 20 chars): {str(token)[:20]}...")

        # 5. Consultar información del comercio
        logger.info(f"Consultando información del comercio {merchant_id}")
        commerce_data = redeban_service.get_commerce_info(
            merchant_id=merchant_id,
            token=token,
            cert_path=cert_path,
            key_path=key_path,
            include_raw_data=include_raw_data
        )

        # 6. Crear respuesta exitosa
        logger.info(f"Procesamiento exitoso para merchant_id: {merchant_id}")
        return create_success_response(commerce_data)

    except ValueError as e:
        logger.warning(f"Error de validación: {str(e)}")
        return create_error_response(str(e), 400)

    except Exception as e:
        logger.error(f"Error en lambda_handler: {str(e)}", exc_info=True)

        # Determinar tipo de error más específico
        error_str = str(e).lower()
        if "no encontrado" in error_str or "not found" in error_str:
            status_code = 404
        elif any(keyword in error_str for keyword in ["autenticación", "token", "authentication", "unauthorized"]):
            status_code = 401
        elif any(keyword in error_str for keyword in ["prohibido", "forbidden", "permisos", "access denied"]):
            status_code = 403
        elif any(keyword in error_str for keyword in ["parámetros", "parameters", "bad request", "validación"]):
            status_code = 400
        elif "timeout" in error_str:
            status_code = 504
        elif any(keyword in error_str for keyword in ["conexión", "connection", "network", "service unavailable"]):
            status_code = 503
        else:
            status_code = 500

        return create_error_response(str(e), status_code)


def extract_merchant_id(event):
    """
    Extrae el MerchantID del evento con mejor manejo de casos
    """
    # API Gateway - pathParameters
    if 'pathParameters' in event and event['pathParameters']:
        merchant_id = event['pathParameters'].get('merchantId')
        if merchant_id:
            return merchant_id.strip()

    # API Gateway - path directo (sin parámetros nombrados)
    if 'path' in event:
        # Extraer de URL path como /commerce/12345678
        path_parts = event['path'].strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[0] == 'commerce':
            return path_parts[1].strip()

    # Invocación directa
    if 'MerchantID' in event:
        return str(event['MerchantID']).strip()

    # Variantes del nombre
    for key in ['merchantId', 'merchant_id', 'MERCHANT_ID']:
        if key in event:
            return str(event[key]).strip()

    # Body JSON
    if 'body' in event and event['body']:
        try:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
            for key in ['MerchantID', 'merchantId', 'merchant_id', 'MERCHANT_ID']:
                if key in body:
                    return str(body[key]).strip()
        except json.JSONDecodeError:
            logger.warning("Error parseando body JSON")

    # Query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        for key in ['merchantId', 'MerchantID', 'merchant_id']:
            if key in event['queryStringParameters']:
                return str(event['queryStringParameters'][key]).strip()

    # Default para testing
    logger.warning("No se encontró MerchantID en el evento, usando valor por defecto")
    return "10203040"


def extract_include_raw_data(event):
    """
    Extrae el parámetro includeRawData del evento
    """
    # Query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        raw_param = event['queryStringParameters'].get('includeRawData', 'false')
        return str(raw_param).lower() in ['true', '1', 'yes', 'y']

    # Body JSON
    if 'body' in event and event['body']:
        try:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
            return bool(body.get('includeRawData', False))
        except json.JSONDecodeError:
            pass

    # Invocación directa
    return bool(event.get('includeRawData', True))  # Default true para desarrollo


def validate_merchant_id(merchant_id):
    """
    Valida que el MerchantID tenga el formato correcto
    """
    if not merchant_id:
        return False

    merchant_id = merchant_id.strip()
    if len(merchant_id) != 8:
        logger.warning(f"MerchantID longitud inválida: {len(merchant_id)} (esperado: 8)")
        return False
    if not merchant_id.isdigit():
        logger.warning(f"MerchantID no numérico: {merchant_id}")
        return False
    return True


def get_request_metadata(event, context):
    """
    Extrae metadata del request para logging
    """
    metadata = {
        'request_id': context.aws_request_id,
        'function_name': context.function_name,
        'remaining_time': context.get_remaining_time_in_millis() if hasattr(context, 'get_remaining_time_in_millis') else None
    }
    if 'requestContext' in event:
        request_context = event['requestContext']
        metadata.update({
            'api_request_id': request_context.get('requestId'),
            'http_method': request_context.get('httpMethod'),
            'stage': request_context.get('stage'),
            'source_ip': request_context.get('identity', {}).get('sourceIp')
        })
    if 'headers' in event:
        headers = event['headers'] or {}
        metadata.update({
            'user_agent': headers.get('User-Agent'),
            'content_type': headers.get('Content-Type'),
            'accept': headers.get('Accept')
        })
    return metadata


def health_check_handler(event, context):
    """
    Handler separado para health checks
    """
    try:
        health_status = {
            'lambda': 'healthy',
            'aws_services': {},
            'external_services': {}
        }
        try:
            aws_service.table.get_item(Key={'id': 'health_check'})
            health_status['aws_services']['dynamodb'] = 'healthy'
        except Exception as e:
            health_status['aws_services']['dynamodb'] = f'unhealthy: {str(e)[:100]}'
        try:
            aws_service.secrets_client.describe_secret(SecretId=aws_service.secret_name)
            health_status['aws_services']['secrets_manager'] = 'healthy'
        except Exception as e:
            health_status['aws_services']['secrets_manager'] = f'unhealthy: {str(e)[:100]}'
        try:
            redeban_health = redeban_service.health_check()
            health_status['external_services']['redeban_api'] = redeban_health
        except Exception as e:
            health_status['external_services']['redeban_api'] = {
                'status': 'unhealthy',
                'error': str(e)[:100]
            }
        from models.responses import create_health_check_response
        return create_health_check_response(health_status)
    except Exception as e:
        logger.error(f"Error en health check: {str(e)}")
        return create_error_response(f"Health check falló: {str(e)}", 503)