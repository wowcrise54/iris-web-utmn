#!/usr/bin/env python3
"""
Test script for OpenCTI plugin enhancements
Run after implementing Tasks 1-3 to verify improvements
"""

import asyncio
import time
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "source"))

def test_retry_logic():
    """Test retry logic implementation"""
    print("\n" + "="*60)
    print("Testing Retry Logic")
    print("="*60)
    
    try:
        from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient
        
        # Check if retry parameters exist
        client = OpenCTIClient(
            url="http://test.local",
            token="test",
            retry_attempts=3,
            retry_delay=0.1
        )
        
        print("✓ Retry parameters accepted")
        print(f"  - retry_attempts: {client.retry_attempts}")
        print(f"  - retry_delay: {client.retry_delay}")
        
        return True
    except Exception as e:
        print(f"✗ Retry logic test failed: {e}")
        return False

def test_caching():
    """Test caching implementation"""
    print("\n" + "="*60)
    print("Testing Caching Layer")
    print("="*60)
    
    try:
        from iris_opencti_module.opencti_handler.cache import OpenCTICache
        
        # Create cache
        cache = OpenCTICache(max_size=100, ttl=300)
        
        # Test basic operations
        cache.set("test_key", {"data": "test_value"})
        result = cache.get("test_key")
        
        if result == {"data": "test_value"}:
            print("✓ Basic cache operations work")
        else:
            print("✗ Cache get/set failed")
            return False
        
        # Test cache stats
        stats = cache.get_stats()
        print(f"✓ Cache stats available:")
        print(f"  - Size: {stats['size']}/{stats['max_size']}")
        print(f"  - Hit rate: {stats['hit_rate']:.2%}")
        
        # Test TTL (global TTL, not per-entry)
        # Just verify cache works with default TTL
        cache2 = OpenCTICache(max_size=100, ttl=0.1)
        cache2.set("expire_test", {"data": "value"})
        assert cache2.get("expire_test") is not None
        
        time.sleep(0.2)
        expired = cache2.get("expire_test")
        
        if expired is None:
            print("✓ TTL expiration works")
        else:
            print("✗ TTL expiration failed")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Caching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_progress_tracking():
    """Test progress tracking"""
    print("\n" + "="*60)
    print("Testing Progress Tracking")
    print("="*60)
    
    try:
        from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
        
        # Check if _update_task_progress exists
        if hasattr(OpenCTIHandler, '_update_task_progress'):
            print("✓ Progress tracking method exists")
            return True
        else:
            print("✗ Progress tracking method not found")
            return False
    except Exception as e:
        print(f"✗ Progress tracking test failed: {e}")
        return False

def test_configuration():
    """Test new configuration options"""
    print("\n" + "="*60)
    print("Testing Configuration Options")
    print("="*60)
    
    try:
        import iris_opencti_module.IrisOpenCTIConfig as config
        
        # Check for new configuration parameters
        param_names = [p['param_name'] for p in config.module_configuration]
        
        new_params = [
            'opencti_cache_enabled',
            'opencti_cache_ttl',
            'opencti_retry_enabled',
            'opencti_retry_attempts',
            'opencti_auto_enrich_alerts'
        ]
        
        missing = []
        for param in new_params:
            if param in param_names:
                print(f"✓ {param} configured")
            else:
                print(f"✗ {param} missing")
                missing.append(param)
        
        if missing:
            print(f"\nMissing configuration: {', '.join(missing)}")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def run_benchmark():
    """Simple benchmark for caching performance"""
    print("\n" + "="*60)
    print("Performance Benchmark (Caching)")
    print("="*60)
    
    try:
        from iris_opencti_module.opencti_handler.cache import OpenCTICache
        
        cache = OpenCTICache(max_size=1000, ttl=300)
        
        # Simulate 100 queries
        num_queries = 100
        
        # First pass (cache misses)
        start = time.time()
        for i in range(num_queries):
            cache.set(f"ioc_{i}", {"data": f"result_{i}"})
        first_pass = time.time() - start
        
        # Second pass (cache hits)
        start = time.time()
        for i in range(num_queries):
            cache.get(f"ioc_{i}")
        second_pass = time.time() - start
        
        stats = cache.get_stats()
        
        print(f"✓ Cache benchmark completed:")
        print(f"  - First pass (writes): {first_pass*1000:.2f}ms")
        print(f"  - Second pass (reads): {second_pass*1000:.2f}ms")
        print(f"  - Cache size: {stats['size']}")
        print(f"  - Hit rate: {stats['hit_rate']:.2%}")
        
        return True
    except Exception as e:
        print(f"✗ Benchmark failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("DFIR-IRIS OpenCTI Plugin Enhancement Tests")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Retry Logic", test_retry_logic()))
    results.append(("Caching", test_caching()))
    results.append(("Progress Tracking", test_progress_tracking()))
    results.append(("Configuration", test_configuration()))
    results.append(("Benchmark", run_benchmark()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Enhancements are working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
