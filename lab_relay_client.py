"""
Interactive Protocol Demo Client.

Use this client from two different PCs against the same deployed relay server
to showcase protocol behavior over WebSockets:
- push_pull
- request_response
- exclusive_pair
"""

import asyncio
import argparse
import json
import logging
import uuid
import ssl

import websockets

import config

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LabRelayClient:
    def __init__(self, relay_uri, protocol_name, role, room, client_id):
        self.relay_uri = relay_uri
        self.protocol_name = protocol_name
        self.role = role
        self.room = room
        self.client_id = client_id
        self.websocket = None
        self.running = False
        self.pending_requests = {}
    
    async def connect(self):
        """Connect to relay server and register hello payload."""
        while self.running:
            try:
                logger.info(f"Connecting to relay server at {self.relay_uri}...")
                
                # Create SSL context for WSS connections
                ssl_context = None
                if self.relay_uri.startswith('wss://'):
                    ssl_context = ssl.create_default_context()
                
                self.websocket = await websockets.connect(
                    self.relay_uri,
                    ping_interval=config.PING_INTERVAL,
                    ssl=ssl_context
                )

                hello_payload = {
                    "type": "hello",
                    "protocol": self.protocol_name,
                    "role": self.role,
                    "room": self.room,
                    "client_id": self.client_id,
                }
                await self.websocket.send(json.dumps(hello_payload))

                response_raw = await asyncio.wait_for(self.websocket.recv(), timeout=config.CONNECTION_TIMEOUT)
                response = json.loads(response_raw)
                if response.get("type") == "error":
                    logger.error("Server rejected connection: %s", response.get("message"))
                    await self.websocket.close()
                    self.websocket = None
                    return False

                logger.info("[OK] Connected to relay server as %s/%s in room '%s'", self.protocol_name, self.role, self.room)
                return True
                
            except Exception as e:
                logger.error(f"Connection failed: {str(e)}")
                logger.info(f"Retrying in {config.RECONNECT_DELAY} seconds...")
                await asyncio.sleep(config.RECONNECT_DELAY)
        
        return False

    async def send_json(self, payload):
        await self.websocket.send(json.dumps(payload))

    def print_help(self):
        print("\nCommands:")
        print("  /help                    Show this help")
        print("  /quit                    Exit")

        if self.protocol_name == "push_pull":
            if self.role == "producer":
                print("  <text>                   Push text to a consumer")
            else:
                print("  /pull                    Pull one queued message")

        elif self.protocol_name == "request_response":
            if self.role == "requester":
                print("  <text>                   Send request payload")
            else:
                print("  /reply <id> <text>       Reply to a request id")

        elif self.protocol_name == "exclusive_pair":
            print("  <text>                   Send chat message to the paired peer")
        print()

    async def receive_loop(self):
        try:
            async for raw in self.websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"[RAW] {raw}")
                    continue

                msg_type = message.get("type")
                if msg_type in {"ack", "no_data", "peer_left", "error"}:
                    print(f"[{msg_type.upper()}] {message.get('message')}")
                    continue

                if self.protocol_name == "push_pull" and msg_type == "push":
                    print(f"[PUSH] from={message.get('from')} payload={message.get('payload')}")
                    continue

                if self.protocol_name == "request_response":
                    if msg_type == "request":
                        request_id = message.get("request_id")
                        payload = message.get("payload")
                        self.pending_requests[request_id] = message
                        print(f"[REQUEST] id={request_id} from={message.get('from')} payload={payload}")
                        print("Use: /reply <request_id> <text>")
                        continue
                    if msg_type == "response":
                        print(
                            "[RESPONSE] id=%s from=%s payload=%s"
                            % (message.get("request_id"), message.get("from"), message.get("payload"))
                        )
                        continue

                if self.protocol_name == "exclusive_pair" and msg_type == "message":
                    print(f"[PEER] {message.get('from')}: {message.get('payload')}")
                    continue

                print(f"[INFO] {message}")
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed by server")
        finally:
            self.running = False

    async def input_loop(self):
        self.print_help()
        while self.running:
            try:
                text = await asyncio.to_thread(input, "> ")
            except EOFError:
                text = "/quit"

            text = text.strip()
            if not text:
                continue

            if text == "/help":
                self.print_help()
                continue

            if text == "/quit":
                self.running = False
                await self.websocket.close()
                break

            if self.protocol_name == "push_pull":
                if self.role == "producer":
                    await self.send_json({"type": "push", "payload": text})
                elif self.role == "consumer":
                    if text != "/pull":
                        print("Consumer only supports: /pull")
                        continue
                    await self.send_json({"type": "pull"})
                continue

            if self.protocol_name == "request_response":
                if self.role == "requester":
                    await self.send_json(
                        {
                            "type": "request",
                            "request_id": uuid.uuid4().hex[:12],
                            "payload": text,
                        }
                    )
                else:
                    if not text.startswith("/reply "):
                        print("Responder only supports: /reply <request_id> <text>")
                        continue

                    parts = text.split(" ", 2)
                    if len(parts) < 3:
                        print("Usage: /reply <request_id> <text>")
                        continue

                    request_id = parts[1].strip()
                    payload = parts[2].strip()
                    await self.send_json(
                        {
                            "type": "response",
                            "request_id": request_id,
                            "payload": payload,
                        }
                    )
                continue

            if self.protocol_name == "exclusive_pair":
                await self.send_json({"type": "message", "payload": text})
    
    async def run(self):
        """Main client loop."""
        self.running = True
        if not await self.connect():
            return

        receiver = asyncio.create_task(self.receive_loop())
        sender = asyncio.create_task(self.input_loop())

        done, pending = await asyncio.wait(
            [receiver, sender],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        for task in done:
            if task.exception():
                logger.error("Client task failed: %s", task.exception())


def parse_args():
    parser = argparse.ArgumentParser(description="Interactive protocol demo client")
    parser.add_argument(
        "--protocol",
        choices=["push_pull", "request_response", "exclusive_pair"],
        required=True,
        help="Protocol demo to run",
    )
    parser.add_argument(
        "--role",
        required=True,
        help="Role for selected protocol: producer/consumer, requester/responder, or peer",
    )
    parser.add_argument("--room", default="demo", help="Room name shared by participants")
    parser.add_argument("--name", default=None, help="Client id shown to other peers")
    parser.add_argument(
        "--server",
        default=config.WORKSHOP_IP,
        help="Relay server hostname (default from config.WORKSHOP_IP)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.SERVER_PORT,
        help="Relay server port (default from config.SERVER_PORT)",
    )
    return parser.parse_args()


def build_relay_uri(server, port):
    protocol = "wss" if port == 443 else "ws"
    if port == 443:
        return f"{protocol}://{server}/protocol"
    return f"{protocol}://{server}:{port}/protocol"


def main():
    args = parse_args()
    relay_uri = build_relay_uri(args.server, args.port)
    client_id = args.name or f"{args.role}-{uuid.uuid4().hex[:6]}"

    print("=" * 72)
    print("PROTOCOL DEMO CLIENT")
    print("=" * 72)
    print(f"Server URI : {relay_uri}")
    print(f"Protocol   : {args.protocol}")
    print(f"Role       : {args.role}")
    print(f"Room       : {args.room}")
    print(f"Client ID  : {client_id}")
    print("=" * 72)
    print("Press Ctrl+C or type /quit to stop\n")

    client = LabRelayClient(
        relay_uri=relay_uri,
        protocol_name=args.protocol,
        role=args.role,
        room=args.room,
        client_id=client_id,
    )
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nStopping client...")
    print("Client stopped")


if __name__ == "__main__":
    main()
