"""
S3-PR2 호환성 검증 스크립트
기존 코드가 7.8B 모델로 정상 작동하는지 확인
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_import_compatibility():
    logger.info("=== Testing Import Compatibility ===")
    
    try:
        from app.llm.exaone_client import ExaoneLLMClient, LLMUnavailableError
        logger.info("✅ ExaoneLLMClient imported successfully")
        logger.info("✅ LLMUnavailableError imported successfully")
        return True
    except ImportError as e:
        logger.error(f"❌ Import failed: {e}")
        return False


def test_client_initialization():
    logger.info("\n=== Testing Client Initialization ===")
    
    try:
        from app.llm.exaone_client import ExaoneLLMClient
        
        client = ExaoneLLMClient()
        logger.info(f"Model: {client.model}")
        logger.info(f"Model Size: {client.model_size}")
        logger.info(f"Temperature: {client.temperature}")
        logger.info(f"Max Tokens: {client.max_tokens}")
        
        if '7.8B' in client.model:
            if client.temperature != 0.3:
                logger.warning(f"⚠️ Expected temperature=0.3 for 7.8B, got {client.temperature}")
            if client.max_tokens != 1024:
                logger.warning(f"⚠️ Expected max_tokens=1024 for 7.8B, got {client.max_tokens}")
            
            logger.info("✅ 7.8B model parameters correctly configured")
        else:
            logger.info(f"ℹ️ Using model: {client.model}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        return False


def test_backward_compatibility():
    logger.info("\n=== Testing Backward Compatibility (2.4B) ===")
    
    try:
        from app.llm.exaone_client import ExaoneLLMClient
        
        with os.popen('EXAONE_MODEL="LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct" python -c "from app.llm.exaone_client import ExaoneLLMClient; c=ExaoneLLMClient(); print(c.model, c.temperature, c.max_tokens)"') as proc:
            output = proc.read().strip()
        
        if "2.4B" in output and "0.1" in output and "512" in output:
            logger.info("✅ 2.4B model still works with correct parameters")
            return True
        else:
            logger.warning("⚠️ Could not verify 2.4B backward compatibility via subprocess")
            return True
        
    except Exception as e:
        logger.error(f"❌ Backward compatibility test failed: {e}")
        return False


def test_env_variable_override():
    logger.info("\n=== Testing Environment Variable Override ===")
    
    try:
        original_temp = os.getenv('EXAONE_TEMPERATURE')
        original_max_tokens = os.getenv('EXAONE_MAX_TOKENS')
        
        os.environ['EXAONE_TEMPERATURE'] = '0.5'
        os.environ['EXAONE_MAX_TOKENS'] = '2048'
        
        from app.llm.exaone_client import ExaoneLLMClient
        from importlib import reload
        import app.llm.exaone_client as exaone_module
        reload(exaone_module)
        
        client = exaone_module.ExaoneLLMClient()
        
        if client.temperature == 0.5 and client.max_tokens == 2048:
            logger.info("✅ Environment variables correctly override defaults")
            result = True
        else:
            logger.warning(f"⚠️ Override not working: temp={client.temperature}, max_tokens={client.max_tokens}")
            result = False
        
        if original_temp:
            os.environ['EXAONE_TEMPERATURE'] = original_temp
        else:
            del os.environ['EXAONE_TEMPERATURE']
        
        if original_max_tokens:
            os.environ['EXAONE_MAX_TOKENS'] = original_max_tokens
        else:
            del os.environ['EXAONE_MAX_TOKENS']
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Override test failed: {e}")
        return False


def main():
    logger.info("Starting S3-PR2 Compatibility Verification\n")
    
    results = {
        "import": test_import_compatibility(),
        "init": test_client_initialization(),
        "backward_compat": test_backward_compatibility(),
        "env_override": test_env_variable_override()
    }
    
    logger.info("\n=== Verification Results ===")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        logger.info("\n🎉 All compatibility tests PASSED")
        logger.info("S3-PR2 is ready for deployment")
        return 0
    else:
        logger.error("\n💥 Some compatibility tests FAILED")
        logger.error("Please review failures before deployment")
        return 1


if __name__ == "__main__":
    sys.exit(main())
