import json
import uuid
from datetime import datetime


def create_success_response(data, status_code=200):
    """
    Crea una respuesta exitosa estándar para API Gateway

    Args:
        data (dict): Datos a incluir en la respuesta
        status_code (int): Código de estado HTTP (default: 200)

    Returns:
        dict: Respuesta formateada para API Gateway
    """
    response_id = str(uuid.uuid4())

    response_body = {
        'success': True,
        'data': data,
        'metadata': {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'response_id': response_id,
            'version': '1.0'
        }
    }

    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'X-Response-ID': response_id,
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        },
        'body': json.dumps(response_body, ensure_ascii=False, default=str, indent=2)
    }


def create_error_response(error_message, status_code=500, error_type=None, details=None):
    """
    Crea una respuesta de error estándar para API Gateway

    Args:
        error_message (str): Mensaje de error descriptivo
        status_code (int): Código de estado HTTP (default: 500)
        error_type (str): Tipo de error específico (opcional)
        details (dict): Detalles adicionales del error (opcional)

    Returns:
        dict: Respuesta de error formateada para API Gateway
    """
    response_id = str(uuid.uuid4())

    # Determinar tipo de error si no se especifica
    if error_type is None:
        error_type = determine_error_type(status_code, error_message)

    error_body = {
        'success': False,
        'error': {
            'type': error_type,
            'message': error_message,
            'code': status_code
        },
        'metadata': {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'response_id': response_id,
            'version': '1.0'
        }
    }

    # Agregar detalles adicionales si se proporcionan
    if details:
        error_body['error']['details'] = details

    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'X-Response-ID': response_id,
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        },
        'body': json.dumps(error_body, ensure_ascii=False, default=str, indent=2)
    }


def determine_error_type(status_code, error_message):
    """
    Determina el tipo de error basado en el código de estado y mensaje

    Args:
        status_code (int): Código de estado HTTP
        error_message (str): Mensaje de error

    Returns:
        str: Tipo de error categorizado
    """
    error_message_lower = error_message.lower()

    # Mapeo de códigos de estado a tipos de error
    status_code_mapping = {
        400: "VALIDATION_ERROR",
        401: "AUTHENTICATION_ERROR",
        403: "AUTHORIZATION_ERROR",
        404: "RESOURCE_NOT_FOUND",
        409: "CONFLICT_ERROR",
        422: "BUSINESS_LOGIC_ERROR",
        429: "RATE_LIMIT_ERROR",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT"
    }

    # Primero intentar por código de estado
    if status_code in status_code_mapping:
        return status_code_mapping[status_code]

    # Luego por contenido del mensaje
    if any(keyword in error_message_lower for keyword in ['no encontrado', 'not found']):
        return "RESOURCE_NOT_FOUND"
    elif any(keyword in error_message_lower for keyword in ['token', 'autenticación', 'authentication']):
        return "AUTHENTICATION_ERROR"
    elif any(keyword in error_message_lower for keyword in ['prohibido', 'forbidden', 'permisos']):
        return "AUTHORIZATION_ERROR"
    elif any(keyword in error_message_lower for keyword in ['validación', 'validation', 'inválido', 'invalid']):
        return "VALIDATION_ERROR"
    elif any(keyword in error_message_lower for keyword in ['certificado', 'certificate']):
        return "CERTIFICATE_ERROR"
    elif any(keyword in error_message_lower for keyword in ['timeout', 'time out']):
        return "TIMEOUT_ERROR"
    elif any(keyword in error_message_lower for keyword in ['conexión', 'connection', 'network']):
        return "NETWORK_ERROR"
    else:
        return "UNKNOWN_ERROR"


def create_health_check_response(health_status):
    """
    Crea respuesta para health check

    Args:
        health_status (dict): Estado de salud de los servicios

    Returns:
        dict: Respuesta de health check
    """
    overall_status = "healthy"

    # Determinar estado general
    if isinstance(health_status, dict):
        for service, status in health_status.items():
            if isinstance(status, dict) and status.get('status') != 'healthy':
                overall_status = "unhealthy"
                break
            elif status != 'healthy':
                overall_status = "unhealthy"
                break

    status_code = 200 if overall_status == "healthy" else 503

    response_data = {
        'status': overall_status,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'services': health_status,
        'version': '1.0'
    }

    return create_success_response(response_data, status_code)


def create_validation_error_response(validation_errors):
    """
    Crea respuesta específica para errores de validación

    Args:
        validation_errors (list): Lista de errores de validación

    Returns:
        dict: Respuesta de error de validación
    """
    error_message = "Errores de validación en los datos de entrada"

    details = {
        'validation_errors': validation_errors,
        'total_errors': len(validation_errors) if isinstance(validation_errors, list) else 1
    }

    return create_error_response(
        error_message=error_message,
        status_code=400,
        error_type="VALIDATION_ERROR",
        details=details
    )


def create_business_error_response(business_error, error_code=None):
    """
    Crea respuesta para errores de lógica de negocio

    Args:
        business_error (str): Descripción del error de negocio
        error_code (str): Código específico del error (opcional)

    Returns:
        dict: Respuesta de error de negocio
    """
    details = {}
    if error_code:
        details['error_code'] = error_code

    return create_error_response(
        error_message=business_error,
        status_code=422,
        error_type="BUSINESS_LOGIC_ERROR",
        details=details if details else None
    )


def create_rate_limit_response(retry_after_seconds=None):
    """
    Crea respuesta para errores de rate limiting

    Args:
        retry_after_seconds (int): Segundos después de los cuales reintentar

    Returns:
        dict: Respuesta de rate limit
    """
    error_message = "Límite de peticiones excedido"

    details = {}
    if retry_after_seconds:
        details['retry_after_seconds'] = retry_after_seconds
        error_message += f". Intente nuevamente en {retry_after_seconds} segundos"

    response = create_error_response(
        error_message=error_message,
        status_code=429,
        error_type="RATE_LIMIT_ERROR",
        details=details if details else None
    )

    # Agregar header Retry-After si se especifica
    if retry_after_seconds:
        response['headers']['Retry-After'] = str(retry_after_seconds)

    return response


def format_commerce_response(commerce_data):
    """
    Formatea específicamente los datos de comercio para la respuesta

    Args:
        commerce_data (dict): Datos del comercio a formatear

    Returns:
        dict: Datos formateados para respuesta
    """
    # Estructura estándar para datos de comercio
    formatted_data = {
        'merchant_id': commerce_data.get('merchant_id'),
        'business_info': {
            'business_name': commerce_data.get('business_name'),
            'status': commerce_data.get('status'),
            'is_active': commerce_data.get('is_active', False),
            'registration_date': commerce_data.get('registration_date')
        },
        'contact_info': commerce_data.get('contact_info', {}),
        'additional_info': {}
    }

    # Agregar información adicional si está disponible
    additional_fields = ['document_number', 'establishment_info', 'economic_activity']
    for field in additional_fields:
        if field in commerce_data:
            formatted_data['additional_info'][field] = commerce_data[field]

    # Agregar datos raw si están incluidos
    if 'raw_data' in commerce_data:
        formatted_data['raw_api_response'] = commerce_data['raw_data']

    # Agregar timestamp de respuesta
    if 'response_timestamp' in commerce_data:
        formatted_data['response_timestamp'] = commerce_data['response_timestamp']

    return formatted_data


def create_cors_preflight_response():
    """
    Crea respuesta para solicitudes OPTIONS (CORS preflight)

    Returns:
        dict: Respuesta CORS preflight
    """
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'Access-Control-Max-Age': '86400',  # 24 horas
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'message': 'CORS preflight successful'})
    }