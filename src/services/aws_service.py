"""
AWS Service integration layer for Redeban KYC Lambda.

This module provides a centralized interface for all AWS service operations:
- SSL certificate retrieval from Secrets Manager
- Token management with DynamoDB
- Lambda function invocation for token refresh
- Error handling and retry logic

Author: DevSecOps Team
Version: 1.0.0
"""

import boto3
import json
import base64
import os
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional
from botocore.exceptions import ClientError
from utils.logger import setup_logger, log_function_call

logger = setup_logger(__name__)


class AWSService:
    """
    AWS services integration class.
    
    Provides unified access to:
    - AWS Secrets Manager for certificate retrieval
    - DynamoDB for token storage and retrieval
    - Lambda for token refresh operations
    """
    
    def __init__(self):
        """Initialize AWS service clients and configuration."""
        # Configuration from environment variables
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.dynamodb_table = os.getenv('DYNAMODB_TABLE', 'RedebanTokens')
        self.secret_name = os.getenv('SECRET_NAME', 'Redeban_Obtener_Token')
        self.token_lambda_name = os.getenv('TOKEN_LAMBDA_NAME', 'lambda_function_obtener_token')
        
        # Initialize AWS clients (reused across invocations)
        self.secrets_client = boto3.client('secretsmanager', region_name=self.region)
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        
        # DynamoDB table reference
        self.table = self.dynamodb.Table(self.dynamodb_table)
        
        logger.info(f"AWSService initialized - Region: {self.region}, Table: {self.dynamodb_table}")
    
    @log_function_call
    def get_certificates(self) -> Tuple[str, str]:
        """
        Retrieve SSL certificates from AWS Secrets Manager.
        
        Downloads base64-encoded certificates and saves them to /tmp directory
        with appropriate file permissions for secure access.
        
        Returns:
            Tuple of (certificate_path, private_key_path)
            
        Raises:
            Exception: If certificates cannot be retrieved or processed
        """
        try:
            logger.info(f"Retrieving certificates from Secrets Manager: {self.secret_name}")
            
            # Get secret value from AWS
            response = self.secrets_client.get_secret_value(SecretId=self.secret_name)
            
            if 'SecretString' not in response:
                raise Exception(f"Secret {self.secret_name} does not contain SecretString")
            
            # Parse JSON secret content
            secret_dict = json.loads(response['SecretString'])
            
            # Validate required keys
            required_keys = ['redeban_crt', 'redeban_key']
            for key in required_keys:
                if key not in secret_dict:
                    raise Exception(f"Secret missing required key: {key}")
                if not secret_dict[key]:
                    raise Exception(f"Empty value for key: {key}")
            
            # File paths in Lambda /tmp directory
            cert_path = "/tmp/redeban.crt"
            key_path = "/tmp/redeban.key"
            
            # Decode and save certificate
            try:
                cert_data = base64.b64decode(secret_dict["redeban_crt"])
                with open(cert_path, "wb") as cert_file:
                    cert_file.write(cert_data)
                os.chmod(cert_path, 0o600)  # Secure permissions
                
            except Exception as e:
                raise Exception(f"Error processing certificate: {str(e)}")
            
            # Decode and save private key
            try:
                key_data = base64.b64decode(secret_dict["redeban_key"])
                with open(key_path, "wb") as key_file:
                    key_file.write(key_data)
                os.chmod(key_path, 0o600)  # Secure permissions
                
            except Exception as e:
                raise Exception(f"Error processing private key: {str(e)}")
            
            # Validate files were created successfully
            if not os.path.exists(cert_path) or os.path.getsize(cert_path) == 0:
                raise Exception("Certificate file empty or not created")
            
            if not os.path.exists(key_path) or os.path.getsize(key_path) == 0:
                raise Exception("Private key file empty or not created")
            
            logger.info("Certificates retrieved and saved successfully")
            return cert_path, key_path
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_messages = {
                'ResourceNotFoundException': f"Secret not found: {self.secret_name}",
                'AccessDeniedException': f"Access denied to secret: {self.secret_name}",
                'InvalidRequestException': f"Invalid request for secret: {self.secret_name}"
            }
            raise Exception(error_messages.get(error_code, f"AWS Secrets Manager error ({error_code}): {str(e)}"))
            
        except json.JSONDecodeError as e:
            raise Exception(f"Error parsing secret JSON: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error retrieving certificates: {str(e)}")
            raise Exception(f"Failed to retrieve certificates: {str(e)}")
    
    @log_function_call
    def get_valid_token(self) -> str:
        """
        Retrieve a valid authentication token from DynamoDB.
        
        Checks for existing token and validates expiration time.
        If no valid token exists, requests a new one via Lambda invocation.
        
        Returns:
            Valid authentication token string
            
        Raises:
            Exception: If no valid token can be obtained
        """
        try:
            logger.info("Checking for existing token in DynamoDB")
            
            # Query for existing token
            response = self.table.get_item(Key={'id': 'token'})
            
            if 'Item' in response:
                token_item = response['Item']
                logger.info("Token found in DynamoDB, validating")
                
                # Check if token is still valid
                if self._is_token_valid(token_item):
                    logger.info("Valid token found in DynamoDB")
                    return token_item['access_token']
                else:
                    logger.info("Token found but expired")
            else:
                logger.info("No token found in DynamoDB")
            
            # Request new token if needed
            logger.info("Requesting new token")
            return self._request_new_token()
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_messages = {
                'ResourceNotFoundException': f"DynamoDB table not found: {self.dynamodb_table}",
                'AccessDeniedException': f"Access denied to DynamoDB table: {self.dynamodb_table}"
            }
            raise Exception(error_messages.get(error_code, f"DynamoDB error ({error_code}): {str(e)}"))
            
        except Exception as e:
            logger.error(f"Error obtaining token: {str(e)}")
            raise Exception(f"Failed to obtain valid token: {str(e)}")
    
    def _is_token_valid(self, token_item: Dict[str, Any]) -> bool:
        """
        Validate if a token is still valid and not expired.
        
        Args:
            token_item: DynamoDB item containing token information
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            # Check if token value exists
            if 'access_token' not in token_item or not token_item['access_token']:
                logger.warning("Token missing access_token value")
                return False
            
            # Calculate expiration based on expires_in and saved date
            if 'expires_in' in token_item and 'fecha_guardado' in token_item:
                try:
                    # Parse saved date
                    saved_date_str = token_item['fecha_guardado']
                    saved_date = datetime.fromisoformat(saved_date_str)
                    
                    # Calculate expiration time
                    expires_in_seconds = int(token_item['expires_in'])
                    expires_at = saved_date + timedelta(seconds=expires_in_seconds)
                    
                    # Current time with safety margin
                    now = datetime.utcnow()
                    safety_margin = timedelta(minutes=5)
                    effective_expiry = expires_at - safety_margin
                    
                    is_valid = now < effective_expiry
                    
                    if is_valid:
                        logger.info(f"Token valid until: {expires_at} (with safety margin)")
                    else:
                        logger.info(f"Token expired. Expires: {expires_at}, Now: {now}")
                    
                    return is_valid
                    
                except Exception as e:
                    logger.warning(f"Error calculating token expiration: {str(e)}")
                    return True  # Assume valid if calculation fails
            
            # Handle legacy expires_at format
            elif 'expires_at' in token_item:
                expires_at_str = token_item['expires_at']
                
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.rstrip('Z'))
                    now = datetime.utcnow()
                    safety_margin = timedelta(minutes=5)
                    effective_expiry = expires_at - safety_margin
                    
                    is_valid = now < effective_expiry
                    
                    if is_valid:
                        logger.info(f"Token valid until: {expires_at} (with safety margin)")
                    else:
                        logger.info(f"Token expired. Expires: {expires_at}, Now: {now}")
                    
                    return is_valid
                    
                except ValueError:
                    logger.warning(f"Invalid date format: {expires_at_str}")
                    return False
            
            else:
                # No expiration info, assume valid
                logger.info("Token has no expiration info, assuming valid")
                return True
                
        except Exception as e:
            logger.error(f"Error validating token: {str(e)}")
            return False
    
    def _request_new_token(self) -> str:
        """
        Request a new token by invoking the token Lambda function.
        
        Returns:
            New authentication token string
            
        Raises:
            Exception: If token cannot be obtained
        """
        try:
            logger.info(f"Invoking token Lambda: {self.token_lambda_name}")
            
            # Invoke token retrieval Lambda
            response = self.lambda_client.invoke(
                FunctionName=self.token_lambda_name,
                InvocationType='RequestResponse',  # Synchronous invocation
                Payload=json.dumps({})
            )
            
            # Check invocation status
            if response['StatusCode'] != 200:
                raise Exception(f"Token Lambda invocation failed. Status: {response['StatusCode']}")
            
            # Check for function errors
            if 'FunctionError' in response:
                error_details = "Unspecified error"
                if 'Payload' in response:
                    try:
                        payload = json.loads(response['Payload'].read().decode('utf-8'))
                        error_details = payload.get('errorMessage', error_details)
                    except:
                        pass
                raise Exception(f"Token Lambda error: {error_details}")
            
            logger.info("Token Lambda invoked successfully")
            
            # Wait for token to be saved to DynamoDB
            import time
            time.sleep(2)
            
            # Retry token retrieval
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Searching for new token in DynamoDB (attempt {attempt + 1})")
                    
                    response = self.table.get_item(Key={'id': 'token'})
                    
                    if 'Item' in response and 'access_token' in response['Item']:
                        token_value = response['Item']['access_token']
                        if token_value:
                            logger.info("New token obtained successfully")
                            return token_value
                    
                    if attempt < max_attempts - 1:
                        logger.warning("Token not found, retrying in 1 second...")
                        time.sleep(1)
                        
                except ClientError as e:
                    logger.error(f"DynamoDB query error: {str(e)}")
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                    else:
                        raise
            
            raise Exception("Token not found after Lambda invocation and retries")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_messages = {
                'ResourceNotFoundException': f"Token Lambda not found: {self.token_lambda_name}",
                'InvalidParameterValueException': f"Invalid parameters for Lambda: {self.token_lambda_name}",
                'TooManyRequestsException': f"Invocation limit exceeded for: {self.token_lambda_name}"
            }
            raise Exception(error_messages.get(error_code, f"AWS Lambda error ({error_code}): {str(e)}"))
            
        except Exception as e:
            logger.error(f"Error requesting new token: {str(e)}")
            raise Exception(f"Failed to obtain new token: {str(e)}")