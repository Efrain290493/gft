"""
Standardized response models for Redeban KYC Lambda API.

This module provides consistent response formatting for:
- Success responses with data and metadata
- Error responses with detailed error information
- Health check responses
- CORS preflight responses

Author: DevSecOps Team
Version: 1.0.0
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Union


def create_success_response(data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
    """
    Create a standardized success response for API Gateway.
    
    Args:
        data: Data to include in the response
        status_code: HTTP status code (default: 200)
        
    Returns:
        Dictionary formatted for API Gateway response
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
        'headers': _get_standard_headers(response_id),
        'body': json.dumps(response_body, ensure_ascii=False, default=str, indent=2)
    }


def create_error_response(
    error_message: str,
    status_code: int = 500,
    error_type: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response for API Gateway.
    
    Args:
        error_message: Descriptive error message
        status_code: HTTP status code (default: 500)
        error_type: Specific error type (optional)
        details: Additional error details (optional)
        
    Returns:
        Dictionary formatted for API Gateway error response
    """
    response_id = str(uuid.uuid4())
    
    # Determine error type if not specified
    if error_type is None:
        error_type = _determine_error_type(status_code, error_message)
    
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
    
    # Add additional details if provided
    if details:
        error_body['error']['details'] = details
    
    return {
        'statusCode': status_code,
        'headers': _get_standard_headers(response_id),
        'body': json.dumps(error_body, ensure_ascii=False, default=str, indent=2)
    }


def create_validation_error_response(validation_errors: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a specific response for validation errors.
    
    Args:
        validation_errors: List of validation error details
        
    Returns:
        Dictionary formatted for validation error response
    """
    error_message = "Validation errors in input data"
    
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


def create_business_error_response(
    business_error: str,
    error_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a response for business logic errors.
    
    Args:
        business_error: Business error description
        error_code: Specific error code (optional)
        
    Returns:
        Dictionary formatted for business error response
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


def create_rate_limit_response(retry_after_seconds: Optional[int] = None) -> Dict[str, Any]:
    """
    Create a response for rate limiting errors.
    
    Args:
        retry_after_seconds: Seconds after which to retry (optional)
        
    Returns:
        Dictionary formatted for rate limit response
    """
    error_message = "API rate limit exceeded"
    
    details = {}
    if retry_after_seconds:
        details['retry_after_seconds'] = retry_after_seconds
        error_message += f". Please retry after {retry_after_seconds} seconds"
    
    response = create_error_response(
        error_message=error_message,
        status_code=429,
        error_type="RATE_LIMIT_ERROR",
        details=details if details else None
    )
    
    # Add Retry-After header if specified
    if retry_after_seconds:
        response['headers']['Retry-After'] = str(retry_after_seconds)
    
    return response


def create_health_check_response(health_status: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a response for health check endpoints.
    
    Args:
        health_status: Health status information for various services
        
    Returns:
        Dictionary formatted for health check response
    """
    overall_status = "healthy"
    
    # Determine overall health status
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


def create_cors_preflight_response() -> Dict[str, Any]:
    """
    Create a response for CORS preflight requests (OPTIONS).
    
    Returns:
        Dictionary formatted for CORS preflight response
    """
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'Access-Control-Max-Age': '86400',  # 24 hours
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'message': 'CORS preflight successful'})
    }


def format_commerce_response(commerce_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format commerce data specifically for API response.
    
    Args:
        commerce_data: Raw commerce data to format
        
    Returns:
        Dictionary with standardized commerce response format
    """
    # Standard commerce response structure
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
    
    # Add additional fields if available
    additional_fields = ['document_number', 'establishment_info', 'economic_activity']
    for field in additional_fields:
        if field in commerce_data:
            formatted_data['additional_info'][field] = commerce_data[field]
    
    # Add raw data if included
    if 'raw_data' in commerce_data:
        formatted_data['raw_api_response'] = commerce_data['raw_data']
    
    # Add response timestamp
    if 'response_timestamp' in commerce_data:
        formatted_data['response_timestamp'] = commerce_data['response_timestamp']
    
    return formatted_data


def _get_standard_headers(response_id: str) -> Dict[str, str]:
    """
    Get standard HTTP headers for API responses.
    
    Args:
        response_id: Unique response identifier
        
    Returns:
        Dictionary of standard HTTP headers
    """
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,OPTIONS',
        'X-Response-ID': response_id,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }


def _determine_error_type(status_code: int, error_message: str) -> str:
    """
    Determine error type based on status code and message content.
    
    Args:
        status_code: HTTP status code
        error_message: Error message string
        
    Returns:
        Categorized error type string
    """
    error_message_lower = error_message.lower()
    
    # Status code to error type mapping
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
    
    # Try status code mapping first
    if status_code in status_code_mapping:
        return status_code_mapping[status_code]
    
    # Then try message content analysis
    error_keywords = {
        "RESOURCE_NOT_FOUND": ['not found', 'no encontrado'],
        "AUTHENTICATION_ERROR": ['token', 'authentication', 'autenticación'],
        "AUTHORIZATION_ERROR": ['forbidden', 'prohibido', 'permission', 'permisos'],
        "VALIDATION_ERROR": ['validation', 'validación', 'invalid', 'inválido'],
        "CERTIFICATE_ERROR": ['certificate', 'certificado'],
        "TIMEOUT_ERROR": ['timeout', 'time out'],
        "NETWORK_ERROR": ['connection', 'network', 'conexión']
    }
    
    for error_type, keywords in error_keywords.items():
        if any(keyword in error_message_lower for keyword in keywords):
            return error_type
    
    return "UNKNOWN_ERROR"


class ResponseBuilder:
    """
    Builder class for creating complex API responses.
    
    Provides a fluent interface for constructing responses with
    multiple data sections and metadata.
    """
    
    def __init__(self):
        """Initialize response builder."""
        self.response_data = {}
        self.response_metadata = {}
        self.response_headers = {}
        self.status_code = 200
    
    def add_data(self, key: str, value: Any) -> 'ResponseBuilder':
        """
        Add data to the response.
        
        Args:
            key: Data key
            value: Data value
            
        Returns:
            Self for method chaining
        """
        self.response_data[key] = value
        return self
    
    def add_metadata(self, key: str, value: Any) -> 'ResponseBuilder':
        """
        Add metadata to the response.
        
        Args:
            key: Metadata key
            value: Metadata value
            
        Returns:
            Self for method chaining
        """
        self.response_metadata[key] = value
        return self
    
    def add_header(self, key: str, value: str) -> 'ResponseBuilder':
        """
        Add header to the response.
        
        Args:
            key: Header key
            value: Header value
            
        Returns:
            Self for method chaining
        """
        self.response_headers[key] = value
        return self
    
    def set_status_code(self, status_code: int) -> 'ResponseBuilder':
        """
        Set HTTP status code.
        
        Args:
            status_code: HTTP status code
            
        Returns:
            Self for method chaining
        """
        self.status_code = status_code
        return self
    
    def build(self) -> Dict[str, Any]:
        """
        Build the final response dictionary.
        
        Returns:
            Complete response dictionary for API Gateway
        """
        response_id = str(uuid.uuid4())
        
        # Prepare response body
        response_body = {
            'success': True,
            'data': self.response_data,
            'metadata': {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'response_id': response_id,
                'version': '1.0',
                **self.response_metadata
            }
        }
        
        # Merge headers
        headers = {
            **_get_standard_headers(response_id),
            **self.response_headers
        }
        
        return {
            'statusCode': self.status_code,
            'headers': headers,
            'body': json.dumps(response_body, ensure_ascii=False, default=str, indent=2)
        }


def create_paginated_response(
    data: List[Dict[str, Any]],
    page: int,
    page_size: int,
    total_count: int,
    additional_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a paginated response for list endpoints.
    
    Args:
        data: List of data items for current page
        page: Current page number (1-based)
        page_size: Number of items per page
        total_count: Total number of items across all pages
        additional_metadata: Additional metadata to include
        
    Returns:
        Dictionary formatted for paginated response
    """
    total_pages = (total_count + page_size - 1) // page_size
    
    pagination_metadata = {
        'pagination': {
            'current_page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'total_count': total_count,
            'has_next': page < total_pages,
            'has_previous': page > 1
        }
    }
    
    if additional_metadata:
        pagination_metadata.update(additional_metadata)
    
    return create_success_response({
        'items': data,
        'pagination': pagination_metadata['pagination']
    })


def create_batch_response(
    results: List[Dict[str, Any]],
    success_count: int,
    error_count: int,
    additional_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a response for batch operations.
    
    Args:
        results: List of individual operation results
        success_count: Number of successful operations
        error_count: Number of failed operations
        additional_info: Additional information to include
        
    Returns:
        Dictionary formatted for batch response
    """
    total_count = success_count + error_count
    
    batch_data = {
        'results': results,
        'summary': {
            'total_processed': total_count,
            'successful': success_count,
            'failed': error_count,
            'success_rate': (success_count / total_count * 100) if total_count > 0 else 0
        }
    }
    
    if additional_info:
        batch_data['additional_info'] = additional_info
    
    # Use appropriate status code based on results
    if error_count == 0:
        status_code = 200  # All successful
    elif success_count == 0:
        status_code = 400  # All failed
    else:
        status_code = 207  # Multi-status (partial success)
    
    return create_success_response(batch_data, status_code)


def create_async_response(
    task_id: str,
    status: str,
    estimated_completion: Optional[str] = None,
    progress_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a response for asynchronous operations.
    
    Args:
        task_id: Unique identifier for the async task
        status: Current task status (pending, processing, completed, failed)
        estimated_completion: Estimated completion time (ISO format)
        progress_info: Additional progress information
        
    Returns:
        Dictionary formatted for async response
    """
    async_data = {
        'task_id': task_id,
        'status': status,
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }
    
    if estimated_completion:
        async_data['estimated_completion'] = estimated_completion
    
    if progress_info:
        async_data['progress'] = progress_info
    
    # Status code based on task status
    status_codes = {
        'pending': 202,
        'processing': 202,
        'completed': 200,
        'failed': 500
    }
    
    status_code = status_codes.get(status, 202)
    
    return create_success_response(async_data, status_code)


def create_cache_response(
    data: Dict[str, Any],
    cache_info: Dict[str, Any],
    max_age: int = 3600
) -> Dict[str, Any]:
    """
    Create a response with cache headers.
    
    Args:
        data: Response data
        cache_info: Cache-related information
        max_age: Cache max age in seconds
        
    Returns:
        Dictionary formatted for cached response
    """
    response = create_success_response(data)
    
    # Add cache-specific headers
    response['headers'].update({
        'Cache-Control': f'public, max-age={max_age}',
        'ETag': cache_info.get('etag', ''),
        'Last-Modified': cache_info.get('last_modified', ''),
        'Expires': (datetime.utcnow() + timedelta(seconds=max_age)).strftime('%a, %d %b %Y %H:%M:%S GMT')
    })
    
    # Add cache info to metadata
    response_body = json.loads(response['body'])
    response_body['metadata']['cache_info'] = cache_info
    response['body'] = json.dumps(response_body, ensure_ascii=False, default=str, indent=2)
    
    return response


def create_redirect_response(
    location: str,
    permanent: bool = False,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a redirect response.
    
    Args:
        location: Target URL for redirection
        permanent: Whether redirect is permanent (301) or temporary (302)
        message: Optional message to include
        
    Returns:
        Dictionary formatted for redirect response
    """
    status_code = 301 if permanent else 302
    
    response_data = {
        'redirect_url': location,
        'permanent': permanent
    }
    
    if message:
        response_data['message'] = message
    
    response = create_success_response(response_data, status_code)
    response['headers']['Location'] = location
    
    return response


def create_file_response(
    file_content: bytes,
    filename: str,
    content_type: str = 'application/octet-stream',
    inline: bool = False
) -> Dict[str, Any]:
    """
    Create a response for file downloads.
    
    Args:
        file_content: File content as bytes
        filename: Name of the file
        content_type: MIME type of the file
        inline: Whether to display inline or as attachment
        
    Returns:
        Dictionary formatted for file response
    """
    import base64
    
    disposition = 'inline' if inline else 'attachment'
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': content_type,
            'Content-Disposition': f'{disposition}; filename="{filename}"',
            'Content-Length': str(len(file_content)),
            'Cache-Control': 'private, no-cache'
        },
        'body': base64.b64encode(file_content).decode('utf-8'),
        'isBase64Encoded': True
    }


# Response validation utilities
def validate_response_schema(response: Dict[str, Any]) -> bool:
    """
    Validate that response follows expected schema.
    
    Args:
        response: Response dictionary to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['statusCode', 'headers', 'body']
    
    # Check required top-level fields
    if not all(field in response for field in required_fields):
        return False
    
    # Check status code is valid
    if not isinstance(response['statusCode'], int) or not (100 <= response['statusCode'] <= 599):
        return False
    
    # Check headers is dict
    if not isinstance(response['headers'], dict):
        return False
    
    # Check body is string
    if not isinstance(response['body'], str):
        return False
    
    # Try to parse body as JSON
    try:
        body_json = json.loads(response['body'])
        if not isinstance(body_json, dict):
            return False
    except json.JSONDecodeError:
        return False
    
    return True


def sanitize_response_data(data: Any) -> Any:
    """
    Sanitize response data to remove sensitive information.
    
    Args:
        data: Data to sanitize
        
    Returns:
        Sanitized data
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Remove sensitive fields
            if key.lower() in ['password', 'token', 'secret', 'key', 'auth']:
                sanitized[key] = '***REDACTED***'
            else:
                sanitized[key] = sanitize_response_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_response_data(item) for item in data]
    else:
        return data