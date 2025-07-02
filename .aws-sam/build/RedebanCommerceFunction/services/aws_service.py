import boto3
import json
import base64
import os
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from utils.logger import setup_logger
logger = setup_logger()


class AWSService:
    """
    Clase que maneja todas las operaciones con servicios AWS
    Esta clase encapsula la lógica para:
    - Obtener certificados desde Secrets Manager
    - Gestionar tokens en DynamoDB
    - Invocar otras funciones Lambda
    """

    def __init__(self):
        """Inicializa la clase con configuración y clientes AWS"""
        # Configuración desde variables de entorno
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.dynamodb_table = os.getenv('DYNAMODB_TABLE', 'RedebanTokens')
        self.secret_name = os.getenv('SECRET_NAME', 'Redeban_Obtener_Token')
        self.token_lambda_name = os.getenv('TOKEN_LAMBDA_NAME', 'lambda_function_obtener_token')

        # Inicializar clientes AWS (se reutilizan entre invocaciones)
        self.secrets_client = boto3.client('secretsmanager', region_name=self.region)
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)

        # Referencia a la tabla DynamoDB
        self.table = self.dynamodb.Table(self.dynamodb_table)

        logger.info(f"AWSService inicializado - Región: {self.region}, Tabla: {self.dynamodb_table}")

    def get_certificates(self):
        """
        Obtiene los certificados desde AWS Secrets Manager y los guarda en /tmp

        Returns:
            tuple: (cert_path, key_path) - Rutas a los archivos de certificado

        Raises:
            Exception: Si no se pueden obtener o procesar los certificados
        """
        try:
            logger.info(f"Obteniendo certificados desde Secrets Manager: {self.secret_name}")

            # Obtener el secret desde AWS
            response = self.secrets_client.get_secret_value(SecretId=self.secret_name)

            if 'SecretString' not in response:
                raise Exception(f"Secret {self.secret_name} no contiene SecretString")

            # Parsear el JSON del secret
            secret_dict = json.loads(response['SecretString'])

            # Validar que tenga las claves necesarias
            required_keys = ['redeban_crt', 'redeban_key']
            for key in required_keys:
                if key not in secret_dict:
                    raise Exception(f"Secret no contiene la clave requerida: {key}")
                if not secret_dict[key]:
                    raise Exception(f"Valor vacío para la clave: {key}")

            # Rutas donde guardar los certificados en /tmp
            cert_path = "/tmp/redeban.crt"
            key_path = "/tmp/redeban.key"

            # Decodificar y guardar certificado
            try:
                cert_data = base64.b64decode(secret_dict["redeban_crt"])
                with open(cert_path, "wb") as cert_file:
                    cert_file.write(cert_data)

                # Establecer permisos restrictivos
                os.chmod(cert_path, 0o600)

            except Exception as e:
                raise Exception(f"Error decodificando/guardando certificado: {str(e)}")

            # Decodificar y guardar llave privada
            try:
                key_data = base64.b64decode(secret_dict["redeban_key"])
                with open(key_path, "wb") as key_file:
                    key_file.write(key_data)

                # Establecer permisos restrictivos
                os.chmod(key_path, 0o600)

            except Exception as e:
                raise Exception(f"Error decodificando/guardando llave privada: {str(e)}")

            # Validar que los archivos existen y tienen contenido
            if not os.path.exists(cert_path) or os.path.getsize(cert_path) == 0:
                raise Exception("Archivo de certificado vacío o no creado")

            if not os.path.exists(key_path) or os.path.getsize(key_path) == 0:
                raise Exception("Archivo de llave privada vacío o no creado")

            logger.info("Certificados obtenidos y guardados exitosamente")
            return cert_path, key_path

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise Exception(f"Secret no encontrado: {self.secret_name}")
            elif error_code == 'AccessDeniedException':
                raise Exception(f"Acceso denegado al secret: {self.secret_name}")
            elif error_code == 'InvalidRequestException':
                raise Exception(f"Solicitud inválida para secret: {self.secret_name}")
            else:
                raise Exception(f"Error de AWS Secrets Manager ({error_code}): {str(e)}")

        except json.JSONDecodeError as e:
            raise Exception(f"Error parseando JSON del secret: {str(e)}")

        except Exception as e:
            logger.error(f"Error obteniendo certificados: {str(e)}")
            raise Exception(f"No se pudieron obtener los certificados: {str(e)}")

    def get_valid_token(self):
        """
        Obtiene un token válido desde DynamoDB.
        Si no existe o está expirado, solicita uno nuevo.

        Returns:
            str: Token de autenticación válido

        Raises:
            Exception: Si no se puede obtener un token válido
        """
        try:
            logger.info("Buscando token existente en DynamoDB")

            # Buscar token existente en DynamoDB
            response = self.table.get_item(Key={'id': 'redeban_token'})

            if 'Item' in response:
                token_item = response['Item']
                logger.info("Token encontrado en DynamoDB, verificando validez")

                # Verificar si el token aún es válido
                if self._is_token_valid(token_item):
                    logger.info("Token válido encontrado en DynamoDB")
                    return token_item['token']
                else:
                    logger.info("Token encontrado pero expirado")
            else:
                logger.info("No se encontró token en DynamoDB")

            # Si llegamos aquí, necesitamos un nuevo token
            logger.info("Solicitando nuevo token")
            return self._request_new_token()

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise Exception(f"Tabla DynamoDB no encontrada: {self.dynamodb_table}")
            elif error_code == 'AccessDeniedException':
                raise Exception(f"Acceso denegado a tabla DynamoDB: {self.dynamodb_table}")
            else:
                raise Exception(f"Error de DynamoDB ({error_code}): {str(e)}")

        except Exception as e:
            logger.error(f"Error obteniendo token: {str(e)}")
            raise Exception(f"No se pudo obtener token válido: {str(e)}")

    def _is_token_valid(self, token_item):
        """
        Verifica si un token aún es válido

        Args:
            token_item (dict): Item de DynamoDB con información del token

        Returns:
            bool: True si el token es válido, False si no
        """
        try:
            # Verificar que tenga los campos necesarios
            if 'expires_at' not in token_item:
                logger.warning("Token sin campo expires_at")
                return False

            if 'token' not in token_item or not token_item['token']:
                logger.warning("Token sin valor")
                return False

            # Convertir string a datetime
            expires_at_str = token_item['expires_at']

            # Manejar diferentes formatos de fecha
            try:
                if expires_at_str.endswith('Z'):
                    expires_at = datetime.fromisoformat(expires_at_str[:-1])
                else:
                    expires_at = datetime.fromisoformat(expires_at_str)
            except ValueError:
                logger.warning(f"Formato de fecha inválido: {expires_at_str}")
                return False

            # Obtener tiempo actual
            now = datetime.utcnow()

            # Dar un margen de seguridad de 5 minutos antes de que expire
            safety_margin = timedelta(minutes=5)
            effective_expiry = expires_at - safety_margin

            is_valid = now < effective_expiry

            if is_valid:
                logger.info(f"Token válido hasta: {expires_at} (margen aplicado)")
            else:
                logger.info(f"Token expirado o cerca de expirar. Expira: {expires_at}, Ahora: {now}")

            return is_valid

        except Exception as e:
            logger.error(f"Error verificando validez del token: {str(e)}")
            return False

    def _request_new_token(self):
        """
        Solicita un nuevo token invocando la lambda correspondiente

        Returns:
            str: Nuevo token obtenido

        Raises:
            Exception: Si no se puede obtener el nuevo token
        """
        try:
            logger.info(f"Invocando lambda de token: {self.token_lambda_name}")

            # Invocar la lambda que obtiene tokens
            response = self.lambda_client.invoke(
                FunctionName=self.token_lambda_name,
                InvocationType='RequestResponse',  # Síncrono
                Payload=json.dumps({})  # Payload vacío
            )

            # Verificar respuesta de la invocación
            if response['StatusCode'] != 200:
                raise Exception(f"Error invocando lambda de token. Status: {response['StatusCode']}")

            # Verificar si hay errores en la ejecución
            if 'FunctionError' in response:
                error_details = "Error no especificado"
                if 'Payload' in response:
                    try:
                        payload = json.loads(response['Payload'].read().decode('utf-8'))
                        error_details = payload.get('errorMessage', error_details)
                    except:
                        pass
                raise Exception(f"Error en lambda de token: {error_details}")

            logger.info("Lambda de token invocada exitosamente")

            # Esperar un momento para que la lambda guarde el token
            import time
            time.sleep(2)

            # Intentar obtener el token varias veces (retry)
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Buscando nuevo token en DynamoDB (intento {attempt + 1})")

                    response = self.table.get_item(Key={'id': 'redeban_token'})

                    if 'Item' in response and 'token' in response['Item']:
                        token_value = response['Item']['token']
                        if token_value:  # Verificar que no esté vacío
                            logger.info("Nuevo token obtenido exitosamente")
                            return token_value

                    if attempt < max_attempts - 1:
                        logger.warning(f"Token no encontrado, reintentando en 1 segundo...")
                        time.sleep(1)

                except ClientError as e:
                    logger.error(f"Error consultando DynamoDB: {str(e)}")
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                    else:
                        raise

            raise Exception("Token no encontrado después de invocar lambda y reintentos")

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise Exception(f"Lambda de token no encontrada: {self.token_lambda_name}")
            elif error_code == 'InvalidParameterValueException':
                raise Exception(f"Parámetros inválidos para lambda: {self.token_lambda_name}")
            elif error_code == 'TooManyRequestsException':
                raise Exception(f"Límite de invocaciones excedido para: {self.token_lambda_name}")
            else:
                raise Exception(f"Error de AWS Lambda ({error_code}): {str(e)}")

        except Exception as e:
            logger.error(f"Error solicitando nuevo token: {str(e)}")
            raise Exception(f"No se pudo obtener nuevo token: {str(e)}")