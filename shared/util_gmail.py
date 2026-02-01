"""
Shared Gmail utilities - used by hooks, agents, and tools.

Provides Gmail API client and common email operations.
"""

import os
import io
import csv
import base64
import json
import logging
import time
import threading
import smtplib
import http.client
from functools import wraps
from email import policy
from email.parser import BytesParser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Optional: pandas for XLSX support
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# Gmail OAuth scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Allowed attachment types for content extraction
PARSEABLE_EXTENSIONS = {'.csv', '.json', '.xlsx', '.xls', '.txt'}
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024  # 5MB limit for parsing


# Cached Gmail service (singleton per worker process)
_gmail_service = None
_gmail_service_lock = threading.Lock()
_gmail_api_lock = threading.Lock()  # Lock for all Gmail API calls


def retry_on_failure(max_retries: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """
    Decorator to retry Gmail API calls on transient failures.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (TimeoutError, ConnectionError, OSError, http.client.HTTPException) as e:
                    # Catch network errors: IncompleteRead, RemoteDisconnected, BadStatusLine, etc.
                    last_exception = e
                    if attempt < max_retries:
                        logging.warning(f"{func.__name__} attempt {attempt + 1} failed with {type(e).__name__}: {e}. Retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logging.error(f"{func.__name__} failed after {max_retries + 1} attempts with {type(e).__name__}: {e}")
                except HttpError as e:
                    # Retry on 5xx errors and rate limits (429)
                    if e.resp.status in (429, 500, 502, 503, 504):
                        last_exception = e
                        if attempt < max_retries:
                            logging.warning(f"{func.__name__} HTTP {e.resp.status} on attempt {attempt + 1}. Retrying in {current_delay}s...")
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            logging.error(f"{func.__name__} failed after {max_retries + 1} attempts: {e}")
                    else:
                        raise  # Don't retry on 4xx errors (except 429)
            
            raise last_exception
        return wrapper
    return decorator


def get_gmail_service():
    """
    Build a Gmail API service using OAuth credentials from environment.
    
    Returns a cached service instance to avoid repeated OAuth refreshes.
    The token is automatically refreshed when expired.
    
    Thread-safe: Uses a lock to prevent concurrent initialization.
    
    Requires environment variables:
    - GMAIL_CLIENT_ID
    - GMAIL_CLIENT_SECRET
    - GMAIL_REFRESH_TOKEN
    """
    global _gmail_service
    
    # Fast path: service already initialized
    if _gmail_service is not None:
        return _gmail_service
    
    # Slow path: need to initialize (with lock for thread safety)
    with _gmail_service_lock:
        # Double-check after acquiring lock (another thread may have initialized)
        if _gmail_service is not None:
            return _gmail_service
        
        client_id = os.getenv("GMAIL_CLIENT_ID")
        client_secret = os.getenv("GMAIL_CLIENT_SECRET")
        refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

        if not client_id or not client_secret or not refresh_token:
            raise RuntimeError("Missing Gmail OAuth env vars (GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN)")

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

        if not creds.valid or creds.expired:
            creds.refresh(Request())

        # Build with extended timeout for Docker environments
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        http = httplib2.Http(timeout=60)
        authed_http = AuthorizedHttp(creds, http=http)
        _gmail_service = build("gmail", "v1", http=authed_http)
        return _gmail_service


@retry_on_failure(max_retries=3, delay=2.0)
def get_unread_message_ids(service, trigger_body: dict = None) -> List[str]:
    """
    Return list of message IDs for unread messages.
    
    Filters for:
    - Unread status
    - In Inbox (skips Spam/Trash)
    - Only from email specified in NUS_EMAIL env variable
    - Time filter based on trigger source:
      * Timer trigger: emails received after (triggered_at - interval_minutes)
      * Manual pull: emails received after 2025-11-30 (hardcoded)
    
    Args:
        service: Gmail API service instance
        trigger_body: Optional trigger message with source, triggered_at, interval_minutes
    
    Returns:
        Empty list if NUS_EMAIL is not set (logs error)
    """
    import os
    import logging
    from datetime import datetime, timedelta
    
    # Read filter email from environment (required)
    from_email = os.getenv("NUS_EMAIL")
    if not from_email:
        logging.error("NUS_EMAIL environment variable is not set - cannot fetch emails")
        return []
    
    # Timer trigger: calculate cutoff time
    triggered_at_str = trigger_body.get("triggered_at")
    interval_minutes = trigger_body.get("interval_minutes")
        
    if triggered_at_str and interval_minutes:
        triggered_at = datetime.fromisoformat(triggered_at_str)
        after_datetime = triggered_at - timedelta(minutes=interval_minutes)
        after_str = after_datetime.strftime("%Y/%m/%d")
        logging.info(f"Timer trigger: fetching emails after {after_datetime.isoformat()}")
    else:
        # Manual pull: use current datetime minus 1 month as cutoff
        after_str = (datetime.utcnow() - timedelta(days=30)).strftime("%Y/%m/%d")
        logging.info(f"Manual pull: fetching emails after {after_str}")
    
    query = (
        "is:unread label:INBOX "
        f"after:{after_str} "
        f"from:{from_email}"
    )
    
    with _gmail_api_lock:
        result = service.users().messages().list(
            userId="me",
            q=query
        ).execute()

    messages = result.get("messages", [])
    return [m["id"] for m in messages]


@retry_on_failure(max_retries=3, delay=2.0)
def fetch_message_raw(service, msg_id: str) -> dict:
    """
    Fetch raw RFC822 message by ID.
    
    Returns Gmail metadata + raw RFC822 content.
    Thread-safe: Uses lock to prevent concurrent Gmail API calls.
    """
    with _gmail_api_lock:
        return (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="raw")
            .execute()
        )


@retry_on_failure(max_retries=3, delay=2.0)
def mark_as_read(service, msg_id: str) -> None:
    """
    Remove UNREAD label from the message.
    Thread-safe: Uses lock to prevent concurrent Gmail API calls.
    """
    logging.info(f"Gmail API: Removing UNREAD label from message {msg_id}")
    with _gmail_api_lock:
        result = service.users().messages().modify(
            userId="me",
            id=msg_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    logging.info(f"Gmail API: mark_as_read response: {result.get('labelIds', [])}")


@retry_on_failure(max_retries=3, delay=2.0)
def send_email(service, to: str, subject: str, body: str, reply_to_message_id: str = None, attachments: list = None, cc: str = None, reply_to: str = None) -> dict:
    """
    Send an email via Gmail API.
    
    Args:
        service: Gmail API service instance
        to: Recipient email address
        subject: Email subject
        body: Email body (HTML or plain text - auto-detected)
        reply_to_message_id: Optional message ID to reply to (for threading)
        attachments: Optional list of dicts with 'filename' and 'content' (str) keys
        cc: Optional CC email address
        reply_to: Optional Reply-To email address (where replies should go)
        cc: Optional CC email address
    
    Returns:
        dict with sent message info
    """
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    
    cc_info = f", cc: {cc}" if cc else ""
    logging.info(f"Gmail API: Sending email to {to}{cc_info}, subject: {subject[:50]}...")
    
    # Auto-detect HTML vs plain text
    is_html = body.strip().startswith('<!DOCTYPE') or body.strip().startswith('<html')
    mime_subtype = "html" if is_html else "plain"
    
    if attachments:
        # Multipart message with attachments
        message = MIMEMultipart()
        message["to"] = to
        if cc:
            message["cc"] = cc
        if reply_to:
            message["Reply-To"] = reply_to
        message["subject"] = subject
        
        # Add body (HTML or plain text)
        message.attach(MIMEText(body, mime_subtype))
        
        # Add attachments
        for att in attachments:
            filename = att.get("filename", "attachment.txt")
            content = att.get("content", "")
            
            part = MIMEBase("application", "octet-stream")
            part.set_payload(content.encode("utf-8") if isinstance(content, str) else content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            message.attach(part)
    else:
        # Simple message (HTML or plain text)
        message = MIMEText(body, mime_subtype)
        message["to"] = to
        if cc:
            message["cc"] = cc
        if reply_to:
            message["Reply-To"] = reply_to
        message["subject"] = subject
    
    # Add threading headers if replying
    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        message["References"] = reply_to_message_id
    
    # Encode message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    
    with _gmail_api_lock:
        result = service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()
    
    logging.info(f"Gmail API: Email sent, message ID: {result.get('id')}")
    return result


def send_email_smtp(
    to: str, 
    subject: str, 
    body: str, 
    cc: Optional[str] = None, 
    attachments: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Send email using SMTP (Office365) instead of Gmail API.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (HTML or plain text, auto-detected)
        cc: Optional CC email address
        attachments: Optional list of attachments [{filename, content}]
    
    Returns:
        Dict with status information
    """
    # Get SMTP configuration from environment
    smtp_host = os.getenv("SMTP_HOST", "smtp.office365.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "")
    
    if not smtp_username or not smtp_password:
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set in environment variables")
    
    # Detect if body is HTML
    is_html = body.strip().startswith('<!DOCTYPE') or body.strip().startswith('<html')
    mime_subtype = "html" if is_html else "plain"
    
    # Build email message
    if attachments:
        message = MIMEMultipart()
        message["From"] = f"{smtp_from_name} <{smtp_username}>" if smtp_from_name else smtp_username
        message["To"] = to
        if cc:
            message["Cc"] = cc
        message["Subject"] = subject
        
        # Add body
        message.attach(MIMEText(body, mime_subtype))
        
        # Add attachments
        for att in attachments:
            filename = att.get("filename", "attachment.txt")
            content = att.get("content", "")
            
            part = MIMEBase("application", "octet-stream")
            part.set_payload(content.encode("utf-8") if isinstance(content, str) else content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            message.attach(part)
    else:
        # Simple message
        message = MIMEText(body, mime_subtype)
        message["From"] = f"{smtp_from_name} <{smtp_username}>" if smtp_from_name else smtp_username
        message["To"] = to
        if cc:
            message["Cc"] = cc
        message["Subject"] = subject
    
    # Send via SMTP
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()  # Upgrade to secure connection
            server.login(smtp_username, smtp_password)
            
            # Build recipient list
            recipients = [to]
            if cc:
                recipients.append(cc)
            
            server.sendmail(smtp_username, recipients, message.as_string())
            
        logging.info(f"SMTP: Email sent to {to} from {smtp_username}")
        return {"status": "sent", "to": to, "from": smtp_username}
    
    except Exception as e:
        logging.error(f"SMTP: Failed to send email - {str(e)}")
        raise


def _parse_attachment_content(filename: str, content_type: str, raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse attachment content for supported file types.
    
    Returns dict with:
    - parsed: True if successfully parsed
    - data: The parsed data (list of dicts for CSV/XLSX, dict/list for JSON)
    - error: Error message if parsing failed
    """
    if len(raw_bytes) > MAX_ATTACHMENT_SIZE:
        return {"parsed": False, "error": f"Attachment too large ({len(raw_bytes)} bytes)"}
    
    ext = os.path.splitext(filename.lower())[1] if filename else ''
    
    try:
        # JSON files
        if ext == '.json' or content_type == 'application/json':
            text = raw_bytes.decode('utf-8')
            data = json.loads(text)
            return {"parsed": True, "data": data, "format": "json"}
        
        # CSV files
        elif ext == '.csv' or content_type == 'text/csv':
            text = raw_bytes.decode('utf-8')
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            return {"parsed": True, "data": rows, "format": "csv", "row_count": len(rows)}
        
        # Excel files (requires pandas)
        elif ext in ('.xlsx', '.xls'):
            if not HAS_PANDAS:
                return {"parsed": False, "error": "pandas not installed for Excel parsing"}
            df = pd.read_excel(io.BytesIO(raw_bytes))
            rows = df.where(pd.notnull(df), None).to_dict(orient='records')
            return {"parsed": True, "data": rows, "format": "excel", "row_count": len(rows)}
        
        # Plain text files
        elif ext == '.txt' or content_type == 'text/plain':
            text = raw_bytes.decode('utf-8')
            try:
                data = json.loads(text)
                return {"parsed": True, "data": data, "format": "json_in_txt"}
            except json.JSONDecodeError:
                pass
            return {"parsed": True, "data": text, "format": "text"}
        
        else:
            return {"parsed": False, "error": f"Unsupported file type: {ext}"}
            
    except json.JSONDecodeError as e:
        return {"parsed": False, "error": f"Invalid JSON: {str(e)}"}
    except UnicodeDecodeError as e:
        return {"parsed": False, "error": f"Encoding error: {str(e)}"}
    except Exception as e:
        logging.exception(f"Failed to parse attachment {filename}")
        return {"parsed": False, "error": f"Parse error: {str(e)}"}


def parse_email_message(msg_data: dict) -> dict:
    """
    Parse raw Gmail message into structured format.
    
    Returns dict with:
    - subject, from, to, date (headers)
    - body_text (plain text body)
    - body_html (HTML body if present)
    - attachments (list of attachment info with parsed content)
    """
    raw_string = msg_data['raw']
    missing_padding = len(raw_string) % 4
    if missing_padding:
        raw_string += '=' * (4 - missing_padding)
    raw_bytes = base64.urlsafe_b64decode(raw_string)
    
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    
    parsed = {
        'message_id': msg_data.get('id'),
        'thread_id': msg_data.get('threadId'),
        'subject': msg.get('subject', ''),
        'from': msg.get('from', ''),
        'to': msg.get('to', ''),
        'cc': msg.get('cc', ''),
        'date': msg.get('date', ''),
        'body_text': '',
        'body_html': '',
        'attachments': []
    }
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition', ''))
            
            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                parsed['body_text'] = part.get_content()
            elif content_type == 'text/html' and 'attachment' not in content_disposition:
                parsed['body_html'] = part.get_content()
            elif 'attachment' in content_disposition or part.get_filename():
                filename = part.get_filename()
                if filename:
                    raw_bytes = part.get_payload(decode=True) or b''
                    attachment_info = {
                        'filename': filename,
                        'content_type': content_type,
                        'size': len(raw_bytes)
                    }
                    
                    ext = os.path.splitext(filename.lower())[1] if filename else ''
                    if ext in PARSEABLE_EXTENSIONS:
                        parse_result = _parse_attachment_content(filename, content_type, raw_bytes)
                        attachment_info['content'] = parse_result
                    
                    parsed['attachments'].append(attachment_info)
    else:
        content_type = msg.get_content_type()
        if content_type == 'text/plain':
            parsed['body_text'] = msg.get_content()
        elif content_type == 'text/html':
            parsed['body_html'] = msg.get_content()
    
    return parsed
