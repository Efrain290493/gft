#!/bin/bash

# Script de deployment para Redeban KYC Lambda
# Uso: ./deploy.sh [environment] [region]

set -e  # Salir si hay algún error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Función para logging con colores
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "${PURPLE}🔹 $1${NC}"
}

# Configuración por defecto
ENVIRONMENT=${1:-dev}
REGION=${2:-us-east-1}
STACK_NAME="redeban-kyc-${ENVIRONMENT}"

# Banner de inicio
echo "🚀 REDEBAN KYC LAMBDA DEPLOYMENT"
echo "================================="
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo "Stack: ${STACK_NAME}"
echo "================================="

# Validar argumentos
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    log_error "Ambiente inválido: $ENVIRONMENT"
    log_info "Ambientes válidos: dev, staging, prod"
    exit 1
fi

# Verificar dependencias
log_step "Verificando dependencias..."

# Verificar AWS CLI
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI no está instalado"
    log_info "Instalar desde: https://aws.amazon.com/cli/"
    exit 1
fi

# Verificar SAM CLI
if ! command -v sam &> /dev/null; then
    log_error "SAM CLI no está instalado"
    log_info "Instalar desde: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
    exit 1
fi

# Verificar Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 no está instalado"
    exit 1
fi

log_success "Todas las dependencias están disponibles"

# Verificar credenciales AWS
log_step "Verificando credenciales AWS..."
if ! aws sts get-caller-identity --region "$REGION" > /dev/null 2>&1; then
    log_error "Credenciales AWS no configuradas o inválidas"
    log_info "Configurar con: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --region "$REGION" --query 'Account' --output text)
USER_ARN=$(aws sts get-caller-identity --region "$REGION" --query 'Arn' --output text)
log_success "Conectado a cuenta AWS: $ACCOUNT_ID"
log_info "Usuario/Role: $USER_ARN"

# Verificar si la lambda de token existe
log_step "Verificando dependencias en AWS..."
TOKEN_LAMBDA_EXISTS=$(aws lambda get-function --function-name lambda_function_obtener_token --region "$REGION" 2>/dev/null || echo "false")

if [ "$TOKEN_LAMBDA_EXISTS" = "false" ]; then
    log_warning "Lambda 'lambda_function_obtener_token' no encontrada"
    log_warning "Esta lambda es requerida para obtener tokens de autenticación"

    if [ "$ENVIRONMENT" = "prod" ]; then
        log_error "En producción esta dependencia es crítica"
        exit 1
    else
        read -p "¿Continuar de todas formas? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelado"
            exit 0
        fi
    fi
else
    log_success "Lambda de token encontrada"
fi

# Verificar secrets
log_step "Verificando secrets en AWS..."
SECRETS_OK=true

for SECRET_NAME in "Redeban_Obtener_Token" "Client_secrets_Rdb"; do
    if ! aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" > /dev/null 2>&1; then
        log_warning "Secret '$SECRET_NAME' no encontrado"
        SECRETS_OK=false
    else
        log_success "Secret '$SECRET_NAME' encontrado"
    fi
done

if [ "$SECRETS_OK" = false ]; then
    log_warning "Algunos secrets no están configurados"
    if [ "$ENVIRONMENT" = "prod" ]; then
        log_error "En producción todos los secrets son requeridos"
        exit 1
    else
        log_info "En ambiente de desarrollo, la aplicación usará valores por defecto"
    fi
fi

# Validaciones pre-deployment
log_step "Ejecutando validaciones pre-deployment..."

# Validar template SAM
log_info "Validando template SAM..."
if ! sam validate --region "$REGION"; then
    log_error "Template SAM inválido"
    exit 1
fi
log_success "Template SAM válido"

# Verificar requirements.txt
if [ ! -f "requirements.txt" ]; then
    log_error "Archivo requirements.txt no encontrado"
    exit 1
fi

# Verificar estructura de código
if [ ! -f "src/app.py" ]; then
    log_error "Archivo src/app.py no encontrado"
    exit 1
fi

if [ ! -d "src/services" ]; then
    log_error "Directorio src/services no encontrado"
    exit 1
fi

log_success "Estructura de proyecto válida"

# Ejecutar tests (solo si pytest está disponible)
if command -v pytest &> /dev/null && [ -d "tests" ]; then
    log_step "Ejecutando tests..."
    if pytest tests/ -v --tb=short; then
        log_success "Tests pasaron exitosamente"
    else
        log_warning "Algunos tests fallaron"
        if [ "$ENVIRONMENT" = "prod" ]; then
            log_error "En producción todos los tests deben pasar"
            exit 1
        else
            read -p "¿Continuar de todas formas? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    fi
else
    log_info "Tests no ejecutados (pytest no disponible o tests no encontrados)"
fi

# Build de la aplicación
log_step "Construyendo aplicación SAM..."
if ! sam build --use-container --cached; then
    log_error "Error en sam build"
    exit 1
fi
log_success "Build completado exitosamente"

# Deploy
log_step "Desplegando a AWS..."

DEPLOY_ARGS=(
    --stack-name "$STACK_NAME"
    --region "$REGION"
    --parameter-overrides "Environment=$ENVIRONMENT"
    --capabilities CAPABILITY_IAM
    --no-fail-on-empty-changeset
    --resolve-s3
)

# Configuraciones específicas por ambiente
if [ "$ENVIRONMENT" = "prod" ]; then
    DEPLOY_ARGS+=(--parameter-overrides "Environment=$ENVIRONMENT" "LogLevel=WARNING")
    log_info "Configuración de producción aplicada"
elif [ "$ENVIRONMENT" = "staging" ]; then
    DEPLOY_ARGS+=(--parameter-overrides "Environment=$ENVIRONMENT" "LogLevel=INFO")
    log_info "Configuración de staging aplicada"
else
    DEPLOY_ARGS+=(--parameter-overrides "Environment=$ENVIRONMENT" "LogLevel=DEBUG")
    log_info "Configuración de desarrollo aplicada"
fi

if ! sam deploy "${DEPLOY_ARGS[@]}"; then
    log_error "Error en sam deploy"
    exit 1
fi

log_success "Deploy completado exitosamente"

# Post-deployment validations
log_step "Ejecutando validaciones post-deployment..."

# Obtener outputs del stack
log_info "Obteniendo información del stack..."
STACK_