import os
import asyncio
import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import mcp.types as types
from mcp.server import Server
import mcp.server.stdio

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

server = Server("gmail")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="send-email",
            description="Send an email",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipient_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["recipient_id", "subject", "message"],
            },
        ),
        types.Tool(
            name="get-unread-emails",
            description="Get unread emails",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    service = get_gmail_service()
    if name == "send-email":
        msg = EmailMessage()
        msg.set_content(arguments["message"])
        msg["To"] = arguments["recipient_id"]
        msg["Subject"] = arguments["subject"]
        user_email = service.users().getProfile(userId='me').execute()["emailAddress"]
        msg["From"] = user_email
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return [types.TextContent(type="text", text="Email sent!")]
    elif name == "get-unread-emails":
        results = service.users().messages().list(userId="me", labelIds=["UNREAD"], maxResults=5).execute()
        messages = results.get("messages", [])
        summaries = []
        for m in messages:
            msg = service.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject"]).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            summaries.append(f"From: {headers.get('From', '')}, Subject: {headers.get('Subject', '')}, ID: {m['id']}")
        return [types.TextContent(type="text", text="\n".join(summaries))]
    else:
        return [types.TextContent(type="text", text="Unknown tool")]

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())