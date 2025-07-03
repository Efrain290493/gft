"""
AWS Lambda handler for Redeban KYC Commerce Lookup.

This module provides the main entry point for the Lambda function that:
1. Extracts merchant ID from incoming events
2. Retrieves SSL certificates from AWS Secrets Manager
3. Obtains authentication tokens from DynamoDB
4. Queries Redeban API for merchant information
5. Returns standardized responses

Author: DevSecOps Team
Version: 1.0.0
"""

import json
import os
from typing import Dict, Any, Optional
from services.aws_service import AWSService
from services.redeban_service import RedebanService
from models.responses import (
    create_success_response,
    create_error_response,
    create_cors_preflight_response
)
from utils.logger import setup_logger, log_execution_time, log_function_call

# Initialize logger
logger = setup_logger(__name__)

# Initialize services (outside handler for container reuse optimization)
aws_service = AWSService()
redeban_service = RedebanService()


@log_execution_time
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for processing commerce lookup requests.
    
    Args:
        event: AWS Lambda event object containing request data
        context: AWS Lambda context object with runtime information
        
    Returns:
        Dict containing HTTP response with status code, headers, and body
        
    Raises:
        Various exceptions are caught and converted to appropriate HTTP responses
    """
    try:
        # Handle CORS preflight requests
        if event.get('httpMethod') == 'OPTIONS':
            return create_cors_preflight_response()
            
        # Log request metadata for observability
        request_metadata = _extract_request_metadata(event, context)
        logger.info("Processing commerce lookup request", extra=request_metadata)
        
        # Extract and validate merchant ID
        merchant_id = _extract_merchant_id(event)
        if not _validate_merchant_id(merchant_id):
            logger.warning(f"Invalid merchant ID format: {merchant_id}")
            return create_error_response(
                "MerchantID must be exactly 8 numeric digits", 
                400
            )
        
        # Extract additional parameters
        include_raw_data = _extract_include_raw_data(event)
        
        logger.info(f"Processing merchant {merchant_id}, include_raw_data={include_raw_data}")
        
        # Get SSL certificates from Secrets Manager
        cert_path, key_path = aws_service.get_certificates()
        
        # Obtain valid authentication token
        token = aws_service.get_valid_token()
        
        # Query merchant information from Redeban API
        commerce_data = redeban_service.get_commerce_info(
            merchant_id=merchant_id,
            token=token,
            cert_path=cert_path,
            key_path=key_path,
            include_raw_data=include_raw_data
        )
        
        logger.info(f"Successfully processed merchant {merchant_id}")
        return create_success_response(commerce_data)
        
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return create_error_response(str(e), 400)
        
    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}", exc_info=True)
        
        # Determine appropriate HTTP status code based on error type
        status_code = _determine_error_status_code(str(e))
        return create_error_response(str(e), status_code)


def _extract_merchant_id(event: Dict[str, Any]) -> str:
    """
    Extract merchant ID from various event sources.
    
    Supports multiple event formats:
    - API Gateway path parameters
    - Direct Lambda invocation
    - JSON body content
    - Query string parameters
    
    Args:
        event: Lambda event object
        
    Returns:
        Merchant ID string, defaults to test value if not found
    """
    # API Gateway path parameters
    if 'pathParameters' in event and event['pathParameters']:
        merchant_id = event['pathParameters'].get('merchantId')
        if merchant_id:
            return merchant_id.strip()
    
    # Direct invocation
    if 'MerchantID' in event:
        return str(event['MerchantID']).strip()
    
    # Alternative naming conventions
    for key in ['merchantId', 'merchant_id', 'MERCHANT_ID']:
        if key in event:
            return str(event[key]).strip()
    
    # JSON body
    if 'body' in event and event['body']:
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            for key in ['MerchantID', 'merchantId', 'merchant_id']:
                if key in body:
                    return str(body[key]).strip()
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON body")
    
    # Query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        for key in ['merchantId', 'MerchantID', 'merchant_id']:
            if key in event['queryStringParameters']:
                return str(event['queryStringParameters'][key]).strip()
    
    # Default test value
    logger.warning("MerchantID not found in event, using default test value")
    return "10203040"


def _extract_include_raw_data(event: Dict[str, Any]) -> bool:
    """
    Extract includeRawData parameter from event.
    
    Args:
        event: Lambda event object
        
    Returns:
        Boolean indicating whether to include raw API response data
    """
    # Query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        raw_param = event['queryStringParameters'].get('includeRawData', 'false')
        return str(raw_param).lower() in ['true', '1', 'yes', 'y']
    
    # JSON body
    if 'body' in event and event['body']:
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            return bool(body.get('includeRawData', False))
        except json.JSONDecodeError:
            pass
    
    # Direct invocation
    return bool(event.get('includeRawData', True))


def _validate_merchant_id(merchant_id: str) -> bool:
    """
    Validate merchant ID format.
    
    Requirements:
    - Must be exactly 8 characters long
    - Must contain only numeric digits
    
    Args:
        merchant_id: Merchant ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not merchant_id:
        return False
    
    merchant_id = merchant_id.strip()
    
    if len(merchant_id) != 8:
        logger.warning(f"Invalid merchant ID length: {len(merchant_id)} (expected: 8)")
        return False
        
    if not merchant_id.isdigit():
        logger.warning(f"Non-numeric merchant ID: {merchant_id}")
        return False
        
    return True


def _determine_error_status_code(error_message: str) -> int:
    """
    Determine appropriate HTTP status code based on error message content.
    
    Args:
        error_message: Error message string
        
    Returns:
        HTTP status code integer
    """
    error_lower = error_message.lower()
    
    # Map error keywords to status codes
    error_mapping = {
        ('not found', 'no encontrado'): 404,
        ('authentication', 'token', 'unauthorized', 'autenticación'): 401,
        ('forbidden', 'prohibido', 'access denied', 'permisos'): 403,
        ('validation', 'parameters', 'bad request', 'validación'): 400,
        ('timeout', 'time out'): 504,
        ('connection', 'network', 'service unavailable', 'conexión'): 503,
    }
    
    for keywords, status_code in error_mapping.items():
        if any(keyword in error_lower for keyword in keywords):
            return status_code
    
    return 500  # Default to internal server error


def _extract_request_metadata(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Extract request metadata for logging and observability.
    
    Args:
        event: Lambda event object
        context: Lambda context object
        
    Returns:
        Dictionary containing request metadata
    """
    metadata = {
        'request_id': context.aws_request_id,
        'function_name': context.function_name,
        'remaining_time_ms': getattr(context, 'get_remaining_time_in_millis', lambda: None)(),
        'memory_limit_mb': getattr(context, 'memory_limit_in_mb', None),
        'function_version': getattr(context, 'function_version', None)
    }
    
    # Add API Gateway specific metadata
    if 'requestContext' in event:
        request_context = event['requestContext']
        metadata.update({
            'api_request_id': request_context.get('requestId'),
            'http_method': request_context.get('httpMethod'),
            'stage': request_context.get('stage'),
            'source_ip': request_context.get('identity', {}).get('sourceIp')
        })
    
    # Add HTTP headers metadata
    if 'headers' in event:
        headers = event['headers'] or {}
        metadata.update({
            'user_agent': headers.get('User-Agent'),
            'content_type': headers.get('Content-Type'),
            'accept': headers.get('Accept')
        })
    
    return metadata


@log_function_call
def health_check_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Health check handler for monitoring service status.
    
    Args:
        event: Lambda event object
        context: Lambda context object
        
    Returns:
        Dict containing health check results
    """
    try:
        health_status = {
            'lambda': 'healthy',
            'aws_services': {},
            'external_services': {}
        }
        
        # Check DynamoDB connectivity
        try:
            aws_service.table.get_item(Key={'id': 'health_check'})
            health_status['aws_services']['dynamodb'] = 'healthy'
        except Exception as e:
            health_status['aws_services']['dynamodb'] = f'unhealthy: {str(e)[:100]}'
        
        # Check Secrets Manager connectivity
        try:
            aws_service.secrets_client.describe_secret(SecretId=aws_service.secret_name)
            health_status['aws_services']['secrets_manager'] = 'healthy'
        except Exception as e:
            health_status['aws_services']['secrets_manager'] = f'unhealthy: {str(e)[:100]}'
        
        # Check Redeban API connectivity
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
        logger.error(f"Health check failed: {str(e)}")
        return create_error_response(f"Health check failed: {str(e)}", 503)