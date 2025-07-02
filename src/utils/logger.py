import logging
import json
import sys
import os
from datetime import datetime


def setup_logger(name=None):
    """
    Configura un logger estructurado para CloudWatch

    Args:
        name (str): Nombre del logger (opcional)

    Returns:
        logging.Logger: Logger configurado
    """
    # Usar el nombre del módulo que llama si no se especifica
    if name is None:
        name = __name__

    logger = logging.getLogger(name)

    # Evitar duplicar handlers si ya está configurado
    if logger.handlers:
        return logger

    # Configurar nivel de logging desde variable de entorno
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Mapear strings a niveles de logging
    level_mapping = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    logger.setLevel(level_mapping.get(log_level, logging.INFO))

    # Crear handler para stdout (CloudWatch captura stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)

    # Usar formatter personalizado para logs estructurados
    formatter = StructuredFormatter()
    handler.setFormatter(formatter)

    # Agregar handler al logger
    logger.addHandler(handler)

    # Evitar que los logs se propaguen al logger raíz
    logger.propagate = False

    return logger


class StructuredFormatter(logging.Formatter):
    """
    Formatter personalizado que genera logs estructurados en formato JSON
    Esto es ideal para CloudWatch y herramientas de análisis de logs
    """

    def format(self, record):
        """
        Formatea el log record como JSON estructurado

        Args:
            record (logging.LogRecord): Record de log a formatear

        Returns:
            str: Log formateado como JSON
        """
        # Información base del log
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Agregar información de AWS Lambda si está disponible
        self._add_lambda_context(log_entry)

        # Agregar información de excepción si está presente
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info)
            }

        # Agregar stack trace si está presente
        if record.stack_info:
            log_entry['stack_info'] = record.stack_info

        # Agregar campos personalizados del record
        self._add_custom_fields(log_entry, record)

        # Convertir a JSON
        try:
            return json.dumps(log_entry, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            # Fallback en caso de error serializando
            fallback_entry = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': 'ERROR',
                'message': f'Error serializando log: {str(e)}',
                'original_message': str(record.getMessage())
            }
            return json.dumps(fallback_entry, ensure_ascii=False)

    def _add_lambda_context(self, log_entry):
        """
        Agrega información de contexto de AWS Lambda si está disponible

        Args:
            log_entry (dict): Entrada de log a modificar
        """
        # Variables de entorno de Lambda
        lambda_vars = {
            'aws_request_id': os.getenv('AWS_REQUEST_ID'),
            'function_name': os.getenv('AWS_LAMBDA_FUNCTION_NAME'),
            'function_version': os.getenv('AWS_LAMBDA_FUNCTION_VERSION'),
            'memory_size': os.getenv('AWS_LAMBDA_FUNCTION_MEMORY_SIZE'),
            'region': os.getenv('AWS_REGION'),
            'execution_env': os.getenv('AWS_EXECUTION_ENV')
        }

        # Solo agregar variables que tienen valor
        aws_context = {k: v for k, v in lambda_vars.items() if v}

        if aws_context:
            log_entry['aws'] = aws_context

    def _add_custom_fields(self, log_entry, record):
        """
        Agrega campos personalizados del record al log

        Args:
            log_entry (dict): Entrada de log a modificar
            record (logging.LogRecord): Record de log original
        """
        # Lista de campos estándar que no queremos duplicar
        standard_fields = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
            'filename', 'module', 'lineno', 'funcName', 'created',
            'msecs', 'relativeCreated', 'thread', 'threadName',
            'processName', 'process', 'getMessage', 'exc_info',
            'exc_text', 'stack_info'
        }

        # Agregar campos personalizados
        custom_fields = {}
        for key, value in record.__dict__.items():
            if key not in standard_fields and not key.startswith('_'):
                custom_fields[key] = value

        if custom_fields:
            log_entry['custom'] = custom_fields


class ContextLogger:
    """
    Logger con contexto que permite agregar información persistente
    Útil para tracking de requests, correlation IDs, etc.
    """

    def __init__(self, logger, context=None):
        """
        Inicializa el logger con contexto

        Args:
            logger (logging.Logger): Logger base
            context (dict): Contexto a agregar a todos los logs
        """
        self.logger = logger
        self.context = context or {}

    def _log_with_context(self, level, message, *args, **kwargs):
        """
        Registra un log agregando el contexto

        Args:
            level (int): Nivel de log
            message (str): Mensaje a loggear
            *args: Argumentos para el mensaje
            **kwargs: Argumentos adicionales
        """
        # Combinar contexto con extra kwargs
        extra = kwargs.get('extra', {})
        extra.update(self.context)
        kwargs['extra'] = extra

        # Loggear con el nivel apropiado
        self.logger.log(level, message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Log nivel DEBUG con contexto"""
        self._log_with_context(logging.DEBUG, message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        """Log nivel INFO con contexto"""
        self._log_with_context(logging.INFO, message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log nivel WARNING con contexto"""
        self._log_with_context(logging.WARNING, message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log nivel ERROR con contexto"""
        self._log_with_context(logging.ERROR, message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log nivel CRITICAL con contexto"""
        self._log_with_context(logging.CRITICAL, message, *args, **kwargs)

    def add_context(self, **kwargs):
        """
        Agrega información al contexto

        Args:
            **kwargs: Pares clave-valor a agregar al contexto
        """
        self.context.update(kwargs)

    def remove_context(self, *keys):
        """
        Remueve claves del contexto

        Args:
            *keys: Claves a remover del contexto
        """
        for key in keys:
            self.context.pop(key, None)

    def clear_context(self):
        """Limpia todo el contexto"""
        self.context.clear()


def get_logger_with_context(name=None, **context):
    """
    Obtiene un logger con contexto pre-configurado

    Args:
        name (str): Nombre del logger
        **context: Contexto inicial para el logger

    Returns:
        ContextLogger: Logger con contexto configurado
    """
    base_logger = setup_logger(name)
    return ContextLogger(base_logger, context)


def log_function_call(func):
    """
    Decorator para loggear automáticamente llamadas a funciones

    Args:
        func (callable): Función a decorar

    Returns:
        callable: Función decorada
    """

    def wrapper(*args, **kwargs):
        logger = setup_logger(func.__module__)

        # Log de entrada
        logger.info(f"Llamando función {func.__name__}", extra={
            'function': func.__name__,
            'args_count': len(args),
            'kwargs_keys': list(kwargs.keys())
        })

        try:
            # Ejecutar función
            result = func(*args, **kwargs)

            # Log de éxito
            logger.info(f"Función {func.__name__} ejecutada exitosamente", extra={
                'function': func.__name__,
                'success': True
            })

            return result

        except Exception as e:
            # Log de error
            logger.error(f"Error en función {func.__name__}: {str(e)}", extra={
                'function': func.__name__,
                'success': False,
                'error_type': type(e).__name__
            }, exc_info=True)

            # Re-lanzar la excepción
            raise

    return wrapper


def log_execution_time(func):
    """
    Decorator para loggear tiempo de ejecución de funciones

    Args:
        func (callable): Función a decorar

    Returns:
        callable: Función decorada
    """
    import time

    def wrapper(*args, **kwargs):
        logger = setup_logger(func.__module__)

        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            execution_time = (time.time() - start_time) * 1000  # En milisegundos

            logger.info(f"Función {func.__name__} completada", extra={
                'function': func.__name__,
                'execution_time_ms': round(execution_time, 2),
                'success': True
            })

            return result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            logger.error(f"Función {func.__name__} falló", extra={
                'function': func.__name__,
                'execution_time_ms': round(execution_time, 2),
                'success': False,
                'error_type': type(e).__name__
            }, exc_info=True)

            raise

    return wrapper