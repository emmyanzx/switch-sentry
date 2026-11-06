"""Sample production incident templates for testing and demonstration."""
from switch_sentry.models import IncidentAlert, IncidentSeverity

SAMPLE_INCIDENTS = [
    IncidentAlert(
        id="INC-P0-CHECKOUT",
        title="Checkout Service 500 Spike on Payment Processing",
        service="checkout-service",
        severity=IncidentSeverity.P0,
        error_name="AttributeError: 'NoneType' object has no attribute 'transaction_id'",
        error_message="'NoneType' object has no attribute 'transaction_id'",
        stack_trace="""Traceback (most recent call last):
  File "checkout/api/routes.py", line 114, in checkout_handler
    result = process_payment(customer_id, order.total)
  File "checkout/services/payment.py", line 42, in process_payment
    transaction_id = response.transaction_id
AttributeError: 'NoneType' object has no attribute 'transaction_id'""",
        affected_file="checkout/services/payment.py",
        line_number=42,
        repo_url="github.com/enterprise/checkout-service",
        commit_hash="9cf1a04",
    ),
    IncidentAlert(
        id="INC-P1-DB-POOL",
        title="Database Connection Pool Exhaustion on /metrics",
        service="analytics-pipeline",
        severity=IncidentSeverity.P1,
        error_name="asyncpg.exceptions.PoolTimeout: connection acquire timeout 10000ms",
        error_message="Connection acquire timeout 10000ms - pool of 50 connections saturated",
        stack_trace="""Traceback (most recent call last):
  File "analytics/server.py", line 88, in get_metrics
    conn = await db_pool.acquire()
  File "asyncpg/pool.py", line 220, in acquire
asyncpg.exceptions.PoolTimeout: could not acquire connection within 10.0s""",
        affected_file="analytics/server.py",
        line_number=88,
        repo_url="github.com/enterprise/analytics-pipeline",
        commit_hash="7b8e391",
    ),
    IncidentAlert(
        id="INC-P2-AUTH-SKEW",
        title="Intermittent Auth Token Rejection across Multi-Region Clusters",
        service="auth-gateway",
        severity=IncidentSeverity.P2,
        error_name="jwt.exceptions.ExpiredSignatureError: Signature has expired",
        error_message="Signature has expired (token issued 2s ago rejected by US-WEST)",
        stack_trace="""Traceback (most recent call last):
  File "gateway/middleware/auth.py", line 35, in verify_token
    claims = verify_auth_token(token)
  File "gateway/security/jwt.py", line 18, in verify_auth_token
    payload = jwt.decode(token, SECRET, algorithms=['HS256'])
jwt.exceptions.ExpiredSignatureError: Signature has expired""",
        affected_file="gateway/security/jwt.py",
        line_number=18,
        repo_url="github.com/enterprise/auth-gateway",
        commit_hash="41a99c2",
    ),
]
