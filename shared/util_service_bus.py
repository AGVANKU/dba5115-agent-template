"""
Service Bus utilities - shared across all layers.

Provides:
- Queue existence checking and creation
- Message publishing to queues
"""

import os
import json
import logging

# Service Bus connection (from environment)
SERVICE_BUS_CONNECTION_STRING = os.getenv("SERVICE_BUS_CONNECTION_STRING")

# Cache for queues we've verified exist (to avoid repeated checks)
_verified_queues: set = set()


def ensure_queue_exists(queue_name: str) -> bool:
    """
    Ensure a Service Bus queue exists, creating it if necessary.
    
    Uses in-memory cache to avoid repeated API calls within the same
    function instance. Idempotent - safe to call every time.
    
    Returns True if queue exists or was created, False on error.
    """
    global _verified_queues
    
    # Skip if already verified this instance
    if queue_name in _verified_queues:
        return True
    
    if not SERVICE_BUS_CONNECTION_STRING:
        logging.warning("SERVICE_BUS_CONNECTION_STRING not configured - cannot verify queue")
        return False
    
    try:
        from azure.servicebus.management import ServiceBusAdministrationClient
        
        with ServiceBusAdministrationClient.from_connection_string(SERVICE_BUS_CONNECTION_STRING) as admin_client:
            # Check if queue exists
            try:
                admin_client.get_queue(queue_name)
                logging.info(f"Queue '{queue_name}' exists")
                _verified_queues.add(queue_name)
                return True
            except Exception as e:
                # Queue doesn't exist - create it
                if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                    logging.info(f"Queue '{queue_name}' not found, creating...")
                    admin_client.create_queue(queue_name)
                    logging.info(f"Queue '{queue_name}' created successfully")
                    _verified_queues.add(queue_name)
                    return True
                else:
                    raise
    except Exception as e:
        logging.exception(f"Failed to ensure queue '{queue_name}' exists: {e}")
        return False


def publish_to_service_bus(
    queue_name: str, 
    message: dict, 
    ensure_queue: bool = True,
    max_retries: int = 1,
    retry_delays: list = None,
    subject: str = None
) -> dict:
    """
    Publish a single message to Service Bus queue with optional retry logic.
    
    Args:
        queue_name: Name of the queue to publish to
        message: Dict to serialize as JSON message body
        ensure_queue: If True, verify/create queue before publishing (default True)
        max_retries: Maximum number of send attempts (default 1, no retries)
        retry_delays: List of delays in seconds between retries (default [2, 5, 10])
        subject: Optional message subject/label
    
    Returns:
        Dict with status, attempts, and optional error details:
        - Success: {"status": "success", "queue": str, "attempts": int}
        - Failure: {"status": "error", "reason": str, "attempts": int}
    """
    if not SERVICE_BUS_CONNECTION_STRING:
        logging.warning("SERVICE_BUS_CONNECTION_STRING not configured - message not sent")
        return {"status": "error", "reason": "Service Bus not configured", "attempts": 0}
    
    # Ensure queue exists before publishing
    if ensure_queue and not ensure_queue_exists(queue_name):
        logging.error(f"Queue '{queue_name}' does not exist and could not be created")
        return {"status": "error", "reason": "Queue does not exist", "attempts": 0}
    
    # Default retry delays if not provided
    if retry_delays is None:
        retry_delays = [2, 5, 10]
    
    # Attempt to publish with retries
    for attempt in range(max_retries):
        try:
            from azure.servicebus import ServiceBusClient, ServiceBusMessage
            import time
            
            with ServiceBusClient.from_connection_string(SERVICE_BUS_CONNECTION_STRING) as client:
                with client.get_queue_sender(queue_name) as sender:
                    # Build message with optional subject
                    message_kwargs = {
                        "body": json.dumps(message),
                        "content_type": "application/json"
                    }
                    if subject:
                        message_kwargs["subject"] = subject
                    
                    sb_message = ServiceBusMessage(**message_kwargs)
                    sender.send_messages(sb_message)
                    
                    logging.info(f"Message published to queue '{queue_name}' (attempt {attempt + 1}/{max_retries})")
                    return {"status": "success", "queue": queue_name, "attempts": attempt + 1}
                    
        except Exception as e:
            is_last_attempt = (attempt == max_retries - 1)
            if is_last_attempt:
                logging.exception(f"Failed to publish to queue '{queue_name}' after {max_retries} attempts: {e}")
                return {"status": "error", "reason": str(e), "attempts": max_retries}
            else:
                # Calculate delay for this attempt
                delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
                logging.warning(f"Publish attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                import time
                time.sleep(delay)
