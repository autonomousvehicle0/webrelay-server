"""
Protocol-Aware Cloud Relay Server.

Supports:
- Legacy vehicle relay: /workshop and /lab
- Push/Pull protocol: /protocol with protocol=push_pull
- Request/Response protocol: /protocol with protocol=request_response
- Exclusive Pair protocol: /protocol with protocol=exclusive_pair
"""

import asyncio
import json
import logging
import os
import uuid
from collections import defaultdict, deque

from aiohttp import web, WSMsgType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RelayServer:
    def __init__(self):
        # Legacy vehicle relay state
        self.workshop_connection = None
        self.lab_connections = set()

        # Protocol demo state
        self.client_sessions = {}
        self.push_pull_rooms = defaultdict(
            lambda: {
                "producers": set(),
                "consumers": set(),
                "queue": deque(),
                "consumer_index": 0,
            }
        )
        self.request_response_rooms = defaultdict(
            lambda: {
                "requesters": set(),
                "responders": set(),
                "responder_index": 0,
                "pending": {},
            }
        )
        self.exclusive_pair_rooms = defaultdict(
            lambda: {
                "peers": [],
            }
        )
        
    async def handle_workshop(self, websocket):
        """Handle workshop (server) connection"""
        logger.info("Workshop connected")
        self.workshop_connection = websocket
        
        try:
            async for msg in websocket:
                if msg.type != WSMsgType.TEXT:
                    continue
                message = msg.data
                # Workshop sends acknowledgments back to lab
                for lab_conn in list(self.lab_connections):
                    try:
                        await lab_conn.send_str(message)
                        logger.debug(f"Forwarded ack from workshop to lab")
                    except Exception as e:
                        logger.error(f"Error sending to lab: {e}")
                        if lab_conn in self.lab_connections:
                            self.lab_connections.remove(lab_conn)
        except Exception as e:
            logger.error(f"Error in handle_workshop: {e}", exc_info=True)
        finally:
            logger.info("Workshop disconnected")
            if self.workshop_connection is websocket:
                self.workshop_connection = None
    
    async def handle_lab(self, websocket):
        """Handle lab (client) connection"""
        logger.info("Lab connected")
        self.lab_connections.add(websocket)
        
        try:
            async for msg in websocket:
                if msg.type != WSMsgType.TEXT:
                    continue
                message = msg.data
                # Forward control data from lab to workshop
                if self.workshop_connection:
                    try:
                        await self.workshop_connection.send_str(message)
                        logger.debug(f"Forwarded message from lab to workshop")
                    except Exception as e:
                        logger.error(f"Error forwarding to workshop: {e}")
                        try:
                            await websocket.send_json({
                                'status': 'error',
                                'message': 'Workshop not connected'
                            })
                        except:
                            pass
                else:
                    logger.warning("No workshop connected, sending error to lab")
                    try:
                        await websocket.send_json({
                            'status': 'error',
                            'message': 'Workshop not connected'
                        })
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error in handle_lab: {e}", exc_info=True)
        finally:
            logger.info("Lab disconnected")
            if websocket in self.lab_connections:
                self.lab_connections.remove(websocket)

    async def send_json(self, websocket, payload):
        await websocket.send_json(payload)

    async def send_error(self, websocket, message, code="error"):
        await self.send_json(
            websocket,
            {
                "type": "error",
                "code": code,
                "message": message,
            },
        )

    async def register_protocol_session(self, websocket, hello):
        protocol = hello.get("protocol")
        role = hello.get("role")
        room = hello.get("room", "default")
        client_id = hello.get("client_id", f"client-{uuid.uuid4().hex[:8]}")

        if protocol not in {"push_pull", "request_response", "exclusive_pair"}:
            await self.send_error(websocket, f"Unsupported protocol: {protocol}", "bad_protocol")
            return None

        if protocol == "push_pull" and role not in {"producer", "consumer"}:
            await self.send_error(websocket, "push_pull role must be producer or consumer", "bad_role")
            return None

        if protocol == "request_response" and role not in {"requester", "responder"}:
            await self.send_error(websocket, "request_response role must be requester or responder", "bad_role")
            return None

        if protocol == "exclusive_pair" and role != "peer":
            await self.send_error(websocket, "exclusive_pair role must be peer", "bad_role")
            return None

        session = {
            "protocol": protocol,
            "role": role,
            "room": room,
            "client_id": client_id,
        }
        self.client_sessions[websocket] = session

        if protocol == "push_pull":
            room_state = self.push_pull_rooms[room]
            room_state[f"{role}s"].add(websocket)

        elif protocol == "request_response":
            room_state = self.request_response_rooms[room]
            room_state[f"{role}s"].add(websocket)

        elif protocol == "exclusive_pair":
            room_state = self.exclusive_pair_rooms[room]
            if len(room_state["peers"]) >= 2:
                await self.send_error(websocket, f"Room '{room}' already has an exclusive pair", "room_full")
                self.client_sessions.pop(websocket, None)
                return None
            room_state["peers"].append(websocket)

        logger.info(
            "Protocol client registered: protocol=%s role=%s room=%s client_id=%s",
            protocol,
            role,
            room,
            client_id,
        )

        await self.send_json(
            websocket,
            {
                "type": "connected",
                "protocol": protocol,
                "role": role,
                "room": room,
                "client_id": client_id,
                "message": "Connected to protocol relay",
            },
        )
        return session

    async def handle_push_pull_message(self, websocket, data, session):
        room_state = self.push_pull_rooms[session["room"]]
        role = session["role"]

        if role == "producer":
            if data.get("type") != "push":
                await self.send_error(websocket, "Producer can only send messages with type='push'", "bad_message")
                return

            payload = data.get("payload")
            envelope = {
                "type": "push",
                "from": session["client_id"],
                "room": session["room"],
                "payload": payload,
            }

            consumers = list(room_state["consumers"])
            if consumers:
                idx = room_state["consumer_index"] % len(consumers)
                consumer = consumers[idx]
                room_state["consumer_index"] += 1
                await self.send_json(consumer, envelope)
                await self.send_json(websocket, {"type": "ack", "message": "Delivered to consumer"})
            else:
                room_state["queue"].append(envelope)
                await self.send_json(websocket, {"type": "ack", "message": "Queued (no consumer online)"})
            return

        if role == "consumer":
            if data.get("type") != "pull":
                await self.send_error(websocket, "Consumer can only send messages with type='pull'", "bad_message")
                return

            if room_state["queue"]:
                envelope = room_state["queue"].popleft()
                await self.send_json(websocket, envelope)
            else:
                await self.send_json(websocket, {"type": "no_data", "message": "Queue is empty"})

    async def handle_request_response_message(self, websocket, data, session):
        room_state = self.request_response_rooms[session["room"]]
        role = session["role"]

        if role == "requester":
            if data.get("type") != "request":
                await self.send_error(websocket, "Requester can only send messages with type='request'", "bad_message")
                return

            responders = list(room_state["responders"])
            if not responders:
                await self.send_error(websocket, "No responder online in this room", "no_responder")
                return

            request_id = data.get("request_id") or uuid.uuid4().hex
            pending_key = (session["room"], request_id)
            if pending_key in room_state["pending"]:
                await self.send_error(websocket, f"request_id already pending: {request_id}", "duplicate_request_id")
                return

            room_state["pending"][pending_key] = websocket
            idx = room_state["responder_index"] % len(responders)
            responder = responders[idx]
            room_state["responder_index"] += 1

            await self.send_json(
                responder,
                {
                    "type": "request",
                    "request_id": request_id,
                    "from": session["client_id"],
                    "room": session["room"],
                    "payload": data.get("payload"),
                },
            )
            await self.send_json(websocket, {"type": "ack", "message": f"Request sent: {request_id}"})
            return

        if role == "responder":
            if data.get("type") != "response":
                await self.send_error(websocket, "Responder can only send messages with type='response'", "bad_message")
                return

            request_id = data.get("request_id")
            if not request_id:
                await self.send_error(websocket, "Missing request_id in response", "missing_request_id")
                return

            pending_key = (session["room"], request_id)
            requester = room_state["pending"].pop(pending_key, None)
            if requester is None:
                await self.send_error(websocket, f"No pending requester for request_id: {request_id}", "unknown_request_id")
                return

            await self.send_json(
                requester,
                {
                    "type": "response",
                    "request_id": request_id,
                    "from": session["client_id"],
                    "room": session["room"],
                    "payload": data.get("payload"),
                },
            )
            await self.send_json(websocket, {"type": "ack", "message": f"Response sent: {request_id}"})

    async def handle_exclusive_pair_message(self, websocket, data, session):
        room_state = self.exclusive_pair_rooms[session["room"]]
        peers = [peer for peer in room_state["peers"] if peer in self.client_sessions]
        room_state["peers"] = peers

        if len(peers) < 2:
            await self.send_error(websocket, "Waiting for second peer to join", "waiting_peer")
            return

        partner = peers[1] if peers[0] is websocket else peers[0]
        payload = data.get("payload")
        await self.send_json(
            partner,
            {
                "type": "message",
                "from": session["client_id"],
                "room": session["room"],
                "payload": payload,
            },
        )

    async def handle_protocol_connection(self, websocket):
        """Handle protocol demo clients on /protocol."""
        try:
            hello_msg = await asyncio.wait_for(websocket.receive(), timeout=15)
        except asyncio.TimeoutError:
            await self.send_error(websocket, "Expected hello message within 15 seconds", "hello_timeout")
            await websocket.close()
            return

        if hello_msg.type != WSMsgType.TEXT:
            await self.send_error(websocket, "First message must be JSON hello payload", "bad_hello")
            await websocket.close()
            return

        try:
            hello = json.loads(hello_msg.data)
        except json.JSONDecodeError:
            await self.send_error(websocket, "First message must be JSON hello payload", "bad_hello")
            await websocket.close()
            return

        if hello.get("type") != "hello":
            await self.send_error(websocket, "First message must have type='hello'", "bad_hello")
            await websocket.close()
            return

        session = await self.register_protocol_session(websocket, hello)
        if session is None:
            await websocket.close()
            return

        try:
            async for msg in websocket:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await self.send_error(websocket, "Message must be valid JSON", "bad_json")
                    continue

                protocol = session["protocol"]
                if protocol == "push_pull":
                    await self.handle_push_pull_message(websocket, data, session)
                elif protocol == "request_response":
                    await self.handle_request_response_message(websocket, data, session)
                elif protocol == "exclusive_pair":
                    await self.handle_exclusive_pair_message(websocket, data, session)
        except Exception as e:
            logger.error("Protocol connection error: %s", e, exc_info=True)
        finally:
            logger.info("Protocol client disconnected: %s", session["client_id"])
            await self.cleanup_protocol_session(websocket)

    async def cleanup_protocol_session(self, websocket):
        session = self.client_sessions.pop(websocket, None)
        if not session:
            return

        protocol = session["protocol"]
        room = session["room"]

        if protocol == "push_pull":
            room_state = self.push_pull_rooms[room]
            room_state[f"{session['role']}s"].discard(websocket)

        elif protocol == "request_response":
            room_state = self.request_response_rooms[room]
            room_state[f"{session['role']}s"].discard(websocket)

            # Remove pending requests for disconnected requester.
            stale_keys = [
                key
                for key, requester in room_state["pending"].items()
                if requester is websocket
            ]
            for key in stale_keys:
                room_state["pending"].pop(key, None)

        elif protocol == "exclusive_pair":
            room_state = self.exclusive_pair_rooms[room]
            if websocket in room_state["peers"]:
                room_state["peers"].remove(websocket)
            for peer in list(room_state["peers"]):
                try:
                    await self.send_json(
                        peer,
                        {
                            "type": "peer_left",
                            "room": room,
                            "message": f"Peer {session['client_id']} disconnected",
                        },
                    )
                except Exception:
                    pass
    
    async def workshop_ws_handler(self, request):
        websocket = web.WebSocketResponse(heartbeat=20)
        await websocket.prepare(request)
        await self.handle_workshop(websocket)
        return websocket

    async def lab_ws_handler(self, request):
        websocket = web.WebSocketResponse(heartbeat=20)
        await websocket.prepare(request)
        await self.handle_lab(websocket)
        return websocket

    async def protocol_ws_handler(self, request):
        websocket = web.WebSocketResponse(heartbeat=20)
        await websocket.prepare(request)
        await self.handle_protocol_connection(websocket)
        return websocket

    async def root_handler(self, request):
        return web.Response(
            text=(
                "Relay server is running. Use WebSocket endpoints: "
                "/workshop, /lab, /protocol"
            )
        )

    async def health_handler(self, request):
        return web.json_response({"status": "ok", "service": "relay"})
    
    def build_app(self):
        """Build and return the aiohttp web application."""
        app = web.Application()
        app.router.add_get("/", self.root_handler)
        app.router.add_get("/health", self.health_handler)
        app.router.add_get("/workshop", self.workshop_ws_handler)
        app.router.add_get("/lab", self.lab_ws_handler)
        app.router.add_get("/protocol", self.protocol_ws_handler)
        return app


def main():
    port = int(os.environ.get("PORT", 8080))
    host = "0.0.0.0"

    logger.info(f"Starting relay server on {host}:{port}")
    logger.info("Workshop should connect to: ws://YOUR_DOMAIN/workshop")
    logger.info("Lab should connect to:      ws://YOUR_DOMAIN/lab")
    logger.info("Protocol clients connect to: ws://YOUR_DOMAIN/protocol")

    relay = RelayServer()
    app = relay.build_app()

    # web.run_app() handles signals, graceful shutdown, and port binding
    # correctly on managed platforms like Render.
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
