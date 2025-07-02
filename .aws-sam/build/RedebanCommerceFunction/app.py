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

        # 2. Obtener certificados desde Secrets Manager
        logger.info("Obteniendo certificados desde Secrets Manager")
        cert_path, key_path = aws_service.get_certificates()

        # 3. Obtener token válido
        logger.info("Obteniendo token de autenticación")
        token = aws_service.get_valid_token()

        # 4. Consultar información del comercio
        logger.info(f"Consultando información del comercio {merchant_id}")
        commerce_data = redeban_service.get_commerce_info(
            merchant_id=merchant_id,
            token=token,
            cert_path=cert_path,
            key_path=key_path
        )

        # 5. Crear respuesta exitosa
        logger.info(f"Procesamiento exitoso para merchant_id: {merchant_id}")
        return create_success_response(commerce_data)

    except ValueError as e:
        logger.warning(f"Error de validación: {str(e)}")
        return create_error_response(str(e), 400)

    except Exception as e:
        logger.error(f"Error en lambda_handler: {str(e)}", exc_info=True)

        # Determinar tipo de error
        if "no encontrado" in str(e).lower() or "not found" in str(e).lower():
            status_code = 404
        elif "autenticación" in str(e).lower() or "token" in str(e).lower():
            status_code = 401
        elif "prohibido" in str(e).lower() or "forbidden" in str(e).lower():
            status_code = 403
        else:
            status_code = 500

        return create_error_response(str(e), status_code)


def extract_merchant_id(event):
    """
    Extrae el MerchantID del evento
    """
    # API Gateway
    if 'pathParameters' in event and event['pathParameters']:
        merchant_id = event['pathParameters'].get('merchantId')
        if merchant_id:
            return merchant_id.strip()

    # Invocación directa
    if 'MerchantID' in event:
        return str(event['MerchantID']).strip()

    # Body JSON
    if 'body' in event and event['body']:
        try:
            body = json.loads(event['body'])
            if 'MerchantID' in body:
                return str(body['MerchantID']).strip()
        except json.JSONDecodeError:
            pass

    # Default para testing
    logger.warning("No se encontró MerchantID en el evento, usando valor por defecto")
    return "10203040"


def validate_merchant_id(merchant_id):
    """
    Valida que el MerchantID tenga el formato correcto
    """
    if not merchant_id:
        return False

    merchant_id = merchant_id.strip()

    if len(merchant_id) != 8:
        return False

    if not merchant_id.isdigit():
        return False

    return True