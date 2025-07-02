#!/usr/bin/env python3
"""
Script para testing local de la función Lambda de Redeban
Permite probar la función sin necesidad de hacer deploy a AWS
"""

import json
import sys
import os
from datetime import datetime

# Agregar el directorio src al path de Python
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
src_dir = os.path.join(parent_dir, 'src')
sys.path.insert(0, src_dir)


class MockContext:
    """
    Mock del contexto de AWS Lambda para testing local
    """

    def __init__(self):
        self.aws_request_id = "local-test-" + str(int(datetime.utcnow().timestamp()))
        self.function_name = "redeban-commerce-lookup-local"
        self.function_version = "$LATEST"
        self.memory_limit_in_mb = 1024
        self.remaining_time_in_millis = lambda: 30000
        self.log_group_name = "/aws/lambda/redeban-commerce-lookup-local"
        self.log_stream_name = "local-test-stream"


def setup_environment():
    """
    Configura las variables de entorno necesarias para testing local
    """
    print("🔧 Configurando variables de entorno...")

    env_vars = {
        'AWS_REGION': 'us-east-1',
        'ENVIRONMENT': 'local',
        'LOG_LEVEL': 'INFO',
        'DYNAMODB_TABLE': 'RedebanTokens-dev',
        'SECRET_NAME': 'Redeban_Obtener_Token',
        'CLIENT_SECRET_NAME': 'Client_secrets_Rdb',
        'TOKEN_LAMBDA_NAME': 'lambda_function_obtener_token',
        'REDEBAN_BASE_URL': 'https://api.qa.sandboxhubredeban.com:9445',
        'REDEBAN_API_PATH': '/rbmcalidad/calidad/api/kyc/v3.0.0/enterprise',
        'REDEBAN_TIMEOUT': '30',
        'REDEBAN_MAX_RETRIES': '3'
    }

    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"   {key} = {value}")


def create_test_events():
    """
    Crea diferentes eventos de prueba

    Returns:
        dict: Diccionario con eventos de prueba
    """
    events = {
        'api_gateway': {
            "pathParameters": {
                "merchantId": "10203040"
            },
            "queryStringParameters": {
                "includeRawData": "true"
            },
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            "httpMethod": "GET",
            "requestContext": {
                "requestId": "local-test-api-gateway",
                "stage": "local"
            }
        },

        'direct_invoke': {
            "MerchantID": "10203040",
            "includeRawData": True
        },

        'invalid_merchant': {
            "MerchantID": "invalid123"
        },

        'missing_merchant': {
            "someOtherField": "value"
        }
    }

    return events


def run_test(event_name, event, context):
    """
    Ejecuta un test específico

    Args:
        event_name (str): Nombre del evento de prueba
        event (dict): Evento a probar
        context: Contexto mock de Lambda

    Returns:
        dict: Resultado del test
    """
    print(f"\n🧪 Ejecutando test: {event_name}")
    print(f"📝 Evento: {json.dumps(event, indent=2)}")

    try:
        # Importar la función Lambda (después de configurar el environment)
        from src.app import lambda_handler

        # Ejecutar la función
        start_time = datetime.utcnow()
        result = lambda_handler(event, context)
        end_time = datetime.utcnow()

        execution_time = (end_time - start_time).total_seconds() * 1000

        print(f"✅ Test {event_name} completado exitosamente")
        print(f"⏱️  Tiempo de ejecución: {execution_time:.2f}ms")
        print(f"📊 Status Code: {result.get('statusCode', 'N/A')}")

        # Parsear y mostrar el body de respuesta
        if 'body' in result:
            try:
                body = json.loads(result['body'])
                print(f"📋 Respuesta:")
                print(json.dumps(body, indent=2, ensure_ascii=False)[:500] + "...")
            except json.JSONDecodeError:
                print(f"📋 Body (raw): {result['body'][:200]}...")

        return {
            'test_name': event_name,
            'success': True,
            'execution_time_ms': execution_time,
            'status_code': result.get('statusCode'),
            'result': result
        }

    except Exception as e:
        print(f"❌ Test {event_name} falló: {str(e)}")
        print(f"🐛 Tipo de error: {type(e).__name__}")

        # Mostrar traceback para debugging
        import traceback
        print(f"📍 Traceback:")
        traceback.print_exc()

        return {
            'test_name': event_name,
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


def run_all_tests():
    """
    Ejecuta todos los tests de la suite

    Returns:
        dict: Resumen de resultados
    """
    print("🚀 Iniciando suite de tests local para Redeban Lambda")
    print("=" * 60)

    # Configurar ambiente
    setup_environment()

    # Crear contexto mock
    context = MockContext()

    # Obtener eventos de prueba
    test_events = create_test_events()

    # Ejecutar tests
    results = []
    for event_name, event in test_events.items():
        result = run_test(event_name, event, context)
        results.append(result)

    # Generar resumen
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE TESTS")
    print("=" * 60)

    total_tests = len(results)
    successful_tests = sum(1 for r in results if r['success'])
    failed_tests = total_tests - successful_tests

    print(f"📈 Tests ejecutados: {total_tests}")
    print(f"✅ Tests exitosos: {successful_tests}")
    print(f"❌ Tests fallidos: {failed_tests}")

    if failed_tests > 0:
        print(f"\n🔍 Tests que fallaron:")
        for result in results:
            if not result['success']:
                print(f"   - {result['test_name']}: {result.get('error', 'Error desconocido')}")

    # Calcular tiempo promedio de ejecución
    successful_times = [r.get('execution_time_ms', 0) for r in results if r['success']]
    if successful_times:
        avg_time = sum(successful_times) / len(successful_times)
        print(f"⏱️  Tiempo promedio de ejecución: {avg_time:.2f}ms")

    success_rate = (successful_tests / total_tests) * 100
    print(f"🎯 Tasa de éxito: {success_rate:.1f}%")

    return {
        'total_tests': total_tests,
        'successful_tests': successful_tests,
        'failed_tests': failed_tests,
        'success_rate': success_rate,
        'results': results
    }


def run_single_test(test_name=None):
    """
    Ejecuta un solo test específico

    Args:
        test_name (str): Nombre del test a ejecutar
    """
    setup_environment()
    context = MockContext()
    test_events = create_test_events()

    if test_name and test_name in test_events:
        run_test(test_name, test_events[test_name], context)
    else:
        print(f"❌ Test '{test_name}' no encontrado")
        print(f"Tests disponibles: {list(test_events.keys())}")


def interactive_mode():
    """
    Modo interactivo para crear eventos personalizados
    """
    print("🎮 Modo interactivo - Crea tu propio evento de prueba")
    print("-" * 50)

    setup_environment()
    context = MockContext()

    # Solicitar merchant_id
    merchant_id = input("Ingresa MerchantID (default: 10203040): ").strip() or "10203040"

    # Solicitar si incluir datos raw
    include_raw = input("¿Incluir datos raw? (y/N): ").strip().lower() in ['y', 'yes', 'sí', 's']

    # Crear evento personalizado
    custom_event = {
        "MerchantID": merchant_id,
        "includeRawData": include_raw
    }

    run_test("custom", custom_event, context)


def main():
    """
    Función principal del script
    """
    import argparse

    parser = argparse.ArgumentParser(description='Script de testing local para Redeban Lambda')
    parser.add_argument('--test', '-t', help='Ejecutar un test específico')
    parser.add_argument('--interactive', '-i', action='store_true', help='Modo interactivo')
    parser.add_argument('--list', '-l', action='store_true', help='Listar tests disponibles')

    args = parser.parse_args()

    if args.list:
        test_events = create_test_events()
        print("Tests disponibles:")
        for test_name in test_events.keys():
            print(f"  - {test_name}")
        return

    if args.interactive:
        interactive_mode()
        return

    if args.test:
        run_single_test(args.test)
        return

    # Ejecutar todos los tests por defecto
    results = run_all_tests()

    # Exit code basado en resultados
    exit_code = 0 if results['failed_tests'] == 0 else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()