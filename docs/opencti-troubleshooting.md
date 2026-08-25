# OpenCTI Plugin Troubleshooting Guide

> **Version:** 1.3.0  
> **Last Updated:** August 2026

---

## Table of Contents

1. [Quick Diagnostic Checklist](#quick-diagnostic-checklist)
2. [Connection Issues](#connection-issues)
3. [Authentication Errors](#authentication-errors)
4. [Enrichment Problems](#enrichment-problems)
5. [Performance Issues](#performance-issues)
6. [Cache and Deduplication Issues](#cache-and-deduplication-issues)
7. [WebSocket and Progress Updates](#websocket-and-progress-updates)
8. [Logging and Debugging](#logging-and-debugging)
9. [Common Error Messages](#common-error-messages)
10. [Recovery Procedures](#recovery-procedures)

---

## Quick Diagnostic Checklist

Run through these steps when encountering issues:

### Initial Diagnostics

- [ ] **Check OpenCTI connectivity**
  ```bash
  curl -X POST https://opencti.example.com/graphql \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "{ about { version } }"}'
  ```

- [ ] **Verify module status in DFIR-IRIS**
  - Navigate to Configuration → Modules
  - Check if IrisOpenCTI is enabled
  - Review module health status

- [ ] **Check logs for errors**
  ```bash
  # IRIS application logs
  tail -f /opt/irisapp/logs/iris.log | grep -i opencti
  
  # Module-specific logs
  tail -f /opt/irisapp/logs/modules.log | grep -i iris_opencti
  ```

- [ ] **Test with a simple IOC**
  - Use a known malicious IOC (e.g., from threat feeds)
  - Try manual enrichment on a test alert
  - Verify results appear correctly

### Common Quick Fixes

| Symptom | Quick Fix |
|---------|-----------|
| Connection timeout | Increase `opencti_timeout` to 30-60 seconds |
| SSL certificate error | Temporarily set `opencti_verify_ssl: false` (dev only) |
| No results returned | Lower `opencti_min_score` to 0 |
| Slow enrichment | Enable caching, reduce `opencti_max_results` |
| Auto-enrich not working | Check Celery worker status |

---

## Connection Issues

### Error: "Cannot connect to OpenCTI"

**Symptoms:**
- Module test connection fails
- Enrichment immediately fails with connection error
- Logs show "Connection refused" or "Failed to establish connection"

**Possible Causes:**
1. OpenCTI URL is incorrect or unreachable
2. Network/firewall blocking connection
3. OpenCTI service is down
4. DNS resolution failure

**Troubleshooting Steps:**

1. **Verify URL format:**
   ```json
   // Correct
   "opencti_url": "https://opencti.example.com"
   
   // Incorrect (missing protocol)
   "opencti_url": "opencti.example.com"
   
   // Incorrect (trailing slash)
   "opencti_url": "https://opencti.example.com/"
   ```

2. **Test network connectivity:**
   ```bash
   # Test basic connectivity
   ping opencti.example.com
   
   # Test HTTP connectivity
   curl -I https://opencti.example.com
   
   # Test GraphQL endpoint
   curl https://opencti.example.com/graphql
   ```

3. **Check firewall rules:**
   ```bash
   # Check if port 443 is open
   telnet opencti.example.com 443
   # or
   nc -zv opencti.example.com 443
   ```

4. **Verify OpenCTI service:**
   ```bash
   # Check OpenCTI service status (if you control the instance)
   systemctl status opencti
   docker ps | grep opencti
   ```

5. **Check proxy configuration:**
   - If using a proxy, ensure `http_proxy` and `https_proxy` are set
   - Verify proxy authentication if required

**Resolution:**
- Correct the URL format
- Open firewall ports (443 for HTTPS)
- Restart OpenCTI service if down
- Configure DNS or use IP address

---

### Error: "SSL certificate verification failed"

**Symptoms:**
- Connection fails with SSL/TLS errors
- Logs show "certificate verify failed" or "SSL: CERTIFICATE_VERIFY_FAILED"

**Possible Causes:**
1. Self-signed certificate
2. Expired certificate
3. Certificate chain incomplete
4. System doesn't trust CA

**Troubleshooting Steps:**

1. **Check certificate:**
   ```bash
   openssl s_client -connect opencti.example.com:443 -showcerts
   ```

2. **Verify certificate validity:**
   ```bash
   openssl s_client -connect opencti.example.com:443 2>/dev/null | \
     openssl x509 -noout -dates
   ```

3. **Check system CA bundle:**
   ```bash
   # Python's certifi bundle
   python -m certifi
   
   # System CA store
   ls -la /etc/ssl/certs/
   ```

**Resolution:**

- **Option 1: Install proper certificate** (recommended for production)
  - Obtain certificate from trusted CA
  - Install on OpenCTI server

- **Option 2: Add certificate to trust store**
  ```bash
  # Download certificate
  openssl s_client -connect opencti.example.com:443 -showcerts > cert.pem
  
  # Add to system trust store (Linux)
  cp cert.pem /usr/local/share/ca-certificates/
  update-ca-certificates
  ```

- **Option 3: Disable verification** (development only)
  ```json
  {
    "opencti_verify_ssl": false
  }
  ```

---

## Authentication Errors

### Error: "Unauthorized" or "401 Unauthorized"

**Symptoms:**
- Connection test fails with 401
- Logs show "unauthorized" or "invalid token"
- Enrichment fails immediately

**Possible Causes:**
1. Invalid or expired API token
2. Token doesn't have required permissions
3. Token format incorrect
4. OpenCTI authentication changed

**Troubleshooting Steps:**

1. **Verify token format:**
   - Token should be a UUID string (36 characters)
   - No extra spaces or characters
   - Example: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`

2. **Test token directly:**
   ```bash
   curl -X POST https://opencti.example.com/graphql \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"query": "{ about { version } }"}'
   ```

3. **Check token permissions in OpenCTI:**
   - Log into OpenCTI web interface
   - Navigate to Settings → Personal Settings
   - Verify API token exists and is active
   - Check role has read permissions for:
     - Indicators
     - StixCyberObservables
     - Relationships

4. **Regenerate token:**
   - Create new token in OpenCTI
   - Update configuration with new token
   - Test connection

**Resolution:**
- Regenerate API token in OpenCTI
- Update `opencti_token` in module configuration
- Ensure token has required read permissions

---

### Error: "Forbidden" or "403 Forbidden"

**Symptoms:**
- Token is valid but access denied
- Can connect but queries fail
- Logs show "forbidden" or "access denied"

**Possible Causes:**
1. Token lacks required permissions
2. OpenCTI role doesn't have necessary access
3. Label-based access control (TLP) restrictions

**Troubleshooting Steps:**

1. **Check OpenCTI role permissions:**
   - Navigate to Settings → Roles in OpenCTI
   - Verify role has "read" access to:
     - Indicators
     - Observables
     - Relationships

2. **Check TLP markings:**
   - Ensure queried entities have appropriate TLP markings
   - User role must have access to TLP level

3. **Test with admin token:**
   - Temporarily use admin token to isolate permission issue
   - If admin works, issue is with user role permissions

**Resolution:**
- Update user role in OpenCTI with required permissions
- Adjust TLP markings on entities
- Use appropriate token with sufficient privileges

---

## Enrichment Problems

### Issue: No Results Returned

**Symptoms:**
- Enrichment completes but shows 0 matches
- IOC is known to be malicious but no OpenCTI data
- Empty enrichment report

**Possible Causes:**
1. IOC not in OpenCTI database
2. `opencti_min_score` too high
3. Search query format issue
4. Entity type mismatch

**Troubleshooting Steps:**

1. **Test search directly in OpenCTI:**
   - Log into OpenCTI web interface
   - Search for the IOC value manually
   - Verify entity exists

2. **Check minimum score setting:**
   ```json
   // Temporarily set to 0 to see all results
   "opencti_min_score": 0,
   "opencti_min_confidence": 0
   ```

3. **Verify IOC format:**
   - Ensure IOC value matches OpenCTI format
   - Check for whitespace or encoding issues
   - Try canonicalized version (lowercase, no trailing dots)

4. **Check entity type support:**
   - Verify IOC type is supported (domain, ipv4, hash, etc.)
   - Some custom types may not be indexed

**Resolution:**
- Lower `opencti_min_score` and `opencti_min_confidence`
- Add IOC to OpenCTI if missing
- Fix IOC format/canonicalization

---

### Issue: Slow Enrichment Performance

**Symptoms:**
- Enrichment takes >30 seconds per IOC
- UI hangs during enrichment
- Timeout errors during enrichment

**Possible Causes:**
1. Large `opencti_max_results` setting
2. Slow OpenCTI instance
3. Network latency
4. No caching enabled
5. Too many related entities fetched

**Troubleshooting Steps:**

1. **Measure query time:**
   ```bash
   # Time a GraphQL query
   time curl -X POST https://opencti.example.com/graphql \
     -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"query": "{ indicators(search: "8.8.8.8", first: 20) { edges { node { id name } } } }"}'
   ```

2. **Check OpenCTI performance:**
   - Monitor OpenCTI server resources
   - Check Elasticsearch/Neo4j performance
   - Review OpenCTI logs for slow queries

3. **Review configuration:**
   ```json
   // Recommended for performance
   {
     "opencti_max_results": 20,
     "opencti_cache_enabled": true,
     "opencti_cache_ttl": 300,
     "opencti_timeout": 20
   }
   ```

4. **Check network latency:**
   ```bash
   ping opencti.example.com
   traceroute opencti.example.com
   ```

**Resolution:**
- Reduce `opencti_max_results` to 10-20
- Enable caching with appropriate TTL
- Increase timeout if network is slow
- Consider dedicated OpenCTI instance for high volume

---

### Issue: Partial Enrichment Failures

**Symptoms:**
- Some IOCs enrich successfully, others fail
- Alert shows "partial" status
- Mixed success/error in batch

**Possible Causes:**
1. Some IOCs trigger errors while others succeed
2. Rate limiting on OpenCTI
3. Transient network issues
4. Different IOC types have different issues

**Troubleshooting Steps:**

1. **Check individual IOC errors:**
   - Review enrichment report for each IOC
   - Look for patterns in failed IOCs
   - Check error messages in logs

2. **Check rate limiting:**
   ```bash
   # Look for 429 responses in logs
   grep "429" /opt/irisapp/logs/iris.log
   ```

3. **Review retry behavior:**
   ```json
   // Ensure retry is enabled
   "opencti_retry_enabled": true,
   "opencti_retry_attempts": 3,
   "opencti_retry_delay": 1
   ```

**Resolution:**
- Increase retry attempts for unstable networks
- Implement rate limiting in batch processor
- Investigate specific IOCs causing failures
- Consider splitting large batches

---

## Performance Issues

### Issue: High Memory Usage

**Symptoms:**
- IRIS server memory usage spikes during enrichment
- Cache size grows unbounded
- System becomes slow

**Possible Causes:**
1. `opencti_cache_size` too high
2. Large enrichment data stored
3. Memory leak in module

**Troubleshooting Steps:**

1. **Check cache size:**
   ```python
   # Check current cache stats
   from iris_opencti_module.opencti_handler.cache import OpenCTICache
   cache = OpenCTICache()
   print(f"Cache size: {cache.size()}, Max: {cache.max_size}")
   ```

2. **Monitor memory:**
   ```bash
   # Monitor IRIS process memory
   ps -o pid,rss,command -p $(pgrep iris)
   
   # Watch memory growth during enrichment
   watch -n 1 'ps -o pid,rss,command -p $(pgrep iris)'
   ```

3. **Review stored enrichment:**
   ```json
   // Disable raw storage if not needed
   "opencti_store_raw_enrichment": false
   ```

**Resolution:**
- Reduce `opencti_cache_size` to 500-1000
- Set `opencti_store_raw_enrichment: false`
- Implement periodic cache cleanup
- Increase server memory if needed

---

### Issue: Database Bloat

**Symptoms:**
- IRIS database grows rapidly
- IOC records very large
- Slow database queries

**Possible Causes:**
1. Raw enrichment data stored for all IOCs
2. Large related entity graphs saved
3. No cleanup of old enrichment data

**Troubleshooting Steps:**

1. **Check IOC enrichment field sizes:**
   ```sql
   -- PostgreSQL query (adjust for your DB)
   SELECT ioc_id, LENGTH(ioc_enrichment) as size
   FROM iocs
   ORDER BY size DESC
   LIMIT 10;
   ```

2. **Review storage settings:**
   ```json
   // Store only summary data
   {
     "opencti_store_raw_enrichment": false,
     "opencti_report_as_attribute": true
   }
   ```

**Resolution:**
- Disable raw enrichment storage
- Use report attribute instead (smaller)
- Implement periodic cleanup of old enrichment data
- Archive old alerts with large enrichment

---

## Cache and Deduplication Issues

### Issue: Stale Cache Data

**Symptoms:**
- Enrichment shows outdated information
- Changes in OpenCTI not reflected
- False sense of security from cached "no match"

**Possible Causes:**
1. Cache TTL too long
2. Cache not invalidated properly
3. OpenCTI data updated but cache not refreshed

**Troubleshooting Steps:**

1. **Check cache TTL:**
   ```json
   // Shorter TTL for frequently-changing data
   "opencti_cache_ttl": 60
   ```

2. **Verify cache invalidation:**
   - Check logs for cache hit/miss patterns
   - Verify TTL expiration is working

3. **Manual cache clear:**
   ```python
   from iris_opencti_module.opencti_handler.cache import OpenCTICache
   cache = OpenCTICache()
   cache.clear()
   ```

**Resolution:**
- Reduce `opencti_cache_ttl` to 60-300 seconds
- Implement cache warming for critical IOCs
- Add cache busting for important lookups

---

### Issue: Deduplication Not Working

**Symptoms:**
- Same IOC enriched multiple times
- Redundant API calls
- Inconsistent results for same IOC

**Possible Causes:**
1. IOC canonicalization issues
2. History TTL expired
3. Different IOC types for same value

**Troubleshooting Steps:**

1. **Check canonicalization:**
   ```python
   from iris_opencti_module.opencti_handler.opencti_mapping import canonicalize_ioc_value
   
   # Test canonicalization
   print(canonicalize_ioc_value("Example.COM", "domain"))
   # Should output: "example.com"
   ```

2. **Check history settings:**
   ```json
   // Longer history TTL
   "opencti_history_ttl_hours": 48
   ```

3. **Review deduplication key:**
   - Ensure same IOC value + type = same dedup key
   - Check for whitespace/encoding issues

**Resolution:**
- Fix canonicalization logic if needed
- Increase history TTL
- Standardize IOC format before enrichment

---

## WebSocket and Progress Updates

### Issue: Progress Updates Not Showing

**Symptoms:**
- Enrichment runs but no progress bar
- UI doesn't show real-time updates
- Socket connection fails

**Possible Causes:**
1. WebSocket not configured in IRIS
2. Socket.IO not enabled
3. Firewall blocking WebSocket
4. JavaScript client not loaded

**Troubleshooting Steps:**

1. **Check Socket.IO configuration:**
   - Verify Flask-SocketIO is configured in IRIS
   - Check WebSocket transport settings

2. **Test WebSocket connection:**
   - Open browser developer tools
   - Check Network tab for WebSocket connection
   - Look for connection errors

3. **Check browser console:**
   - Open browser console (F12)
   - Look for JavaScript errors
   - Verify Socket.IO client loaded

4. **Verify progress callback:**
   ```python
   # In handler, check callback is set
   if handler._progress_callback:
       print("Progress callback configured")
   else:
       print("No progress callback!")
   ```

**Resolution:**
- Enable WebSocket in IRIS configuration
- Ensure Socket.IO is properly initialized
- Fix JavaScript client loading issues
- Check firewall allows WebSocket upgrades

---

## Logging and Debugging

### Enable Debug Logging

**In IRIS configuration:**
```python
# Add to logging configuration
{
  "loggers": {
    "iris_opencti_module": {
      "level": "DEBUG",
      "handlers": ["console", "file"],
      "propagate": false
    }
  }
}
```

**Log locations:**
- `/opt/irisapp/logs/iris.log` - Main application log
- `/opt/irisapp/logs/modules.log` - Module-specific logs
- `/var/log/iris/opencti.log` - OpenCTI module log (if configured)

### Common Log Messages

**INFO level:**
```
Searching OpenCTI for IOC 8.8.8.8
OpenCTI enrichment completed
Added batch of 10 IOCs to queue
```

**WARNING level:**
```
Unable to load related OpenCTI entities for entity-123
Cache miss for IOC: malicious.example.com
```

**ERROR level:**
```
OpenCTI lookup failed for 192.168.1.100: Connection timeout
All 3 retry attempts failed: Unauthorized
Auto-enrichment failed for alert 123
```

### Debug Mode

Enable detailed debugging for troubleshooting:

```json
{
  "opencti_timeout": 60,
  "opencti_retry_attempts": 5,
  "opencti_cache_enabled": false  // Disable cache for debugging
}
```

---

## Common Error Messages

### Connection Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Connection refused` | OpenCTI not running or wrong port | Check OpenCTI service status |
| `Name or service not known` | DNS resolution failure | Use IP address or fix DNS |
| `Connection timed out` | Network unreachable or firewall | Check firewall rules |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Invalid SSL certificate | Install valid cert or disable verification (dev) |

### Authentication Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Unauthorized` | Invalid token | Regenerate token |
| `Forbidden` | Insufficient permissions | Update OpenCTI role |
| `Token expired` | Token rotated/expired | Generate new token |

### Query Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Cannot query field` | OpenCTI version mismatch | Update module or OpenCTI |
| `Unknown argument` | GraphQL query incompatibility | Use fallback queries |
| `Timeout` | Query too slow | Increase timeout or reduce results |

### Data Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `No results found` | IOC not in OpenCTI | Add to OpenCTI or lower score threshold |
| `Invalid IOC format` | Malformed IOC value | Canonicalize IOC before enrichment |
| `Empty response` | OpenCTI returned no data | Check OpenCTI directly |

---

## Recovery Procedures

### Reset Module Configuration

1. **Backup current config:**
   ```bash
   # Export current configuration
   curl -X GET https://iris.example.com/api/modules/iris_opencti_module/config \
     -H "Authorization: Bearer IRIS_TOKEN" > opencti_config_backup.json
   ```

2. **Reset to defaults:**
   - Navigate to Configuration → Modules in IRIS
   - Delete IrisOpenCTI module
   - Re-add module with default settings
   - Reconfigure required parameters

3. **Test fresh configuration:**
   - Use "Test Connection" button
   - Try enrichment on test alert

---

### Clear Cache and History

**Clear in-memory cache:**
```python
from iris_opencti_module.opencti_handler.cache import OpenCTICache
from iris_opencti_module.opencti_handler.history import EnrichmentHistory

# Clear cache
cache = OpenCTICache()
cache.clear()

# Clear history
history = EnrichmentHistory()
history.clear_all()
```

**Clear stored enrichment data:**
```sql
-- Clear enrichment data from IOCs (use with caution!)
UPDATE iocs SET ioc_enrichment = NULL WHERE ioc_enrichment->'opencti' IS NOT NULL;
```

---

### Rebuild Enrichment Data

For alerts with corrupted enrichment:

1. **Identify affected alerts:**
   ```sql
   SELECT alert_id FROM alerts 
   WHERE alert_context->'opencti' IS NOT NULL;
   ```

2. **Clear enrichment:**
   ```sql
   UPDATE iocs 
   SET ioc_enrichment = NULL, ioc_tags = REGEXP_REPLACE(ioc_tags, 'opencti:[^,]*,?', '', 'g')
   WHERE ioc_enrichment->'opencti' IS NOT NULL;
   ```

3. **Re-enrich alerts:**
   - Use manual enrichment action
   - Or trigger auto-enrichment if enabled

---

### Rollback to Previous Version

If recent changes caused issues:

1. **Identify working version:**
   ```bash
   # Check git history
   git log --oneline source/iris_opencti_module/
   ```

2. **Checkout previous version:**
   ```bash
   git checkout <commit-hash> -- source/iris_opencti_module/
   ```

3. **Restart IRIS service:**
   ```bash
   systemctl restart iris
   ```

---

## Getting Help

### When to Contact Support

Contact DFIR-IRIS support when:
- Issue persists after following troubleshooting steps
- Suspect bug in the module
- Need assistance with complex configuration
- Performance issues cannot be resolved

### Information to Provide

When reporting issues, include:

1. **Environment details:**
   - DFIR-IRIS version
   - OpenCTI version
   - Module version
   - Python version
   - Operating system

2. **Configuration:**
   - Full module configuration (sanitize tokens!)
   - Relevant environment variables

3. **Logs:**
   - Error messages from logs
   - Stack traces for exceptions
   - Request/response logs (if applicable)

4. **Reproduction steps:**
   - Exact steps to reproduce
   - Test IOC values
   - Expected vs. actual behavior

---

## Support Contacts

- **DFIR-IRIS Community:** https://community.dfir-iris.org/
- **GitHub Issues:** [Project repository issues](https://github.com/your-repo/issues)
- **Email:** support@dfir-iris.org

---

*This troubleshooting guide is part of the comprehensive DFIR-IRIS OpenCTI plugin documentation.*
