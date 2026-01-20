"""
Simple Cloud Relay Server for Vehicle Control System

This relay server can be deployed on a free cloud service (like Render, Railway, or Heroku)
to forward WebSocket connections between lab and workshop over the internet.

Deploy this to a free cloud service, then:
- Workshop connects to relay as "server"
- Lab connects to relay as "client"
- Relay forwards messages between them
"""

import asyncio
import websockets
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RelayServer:
    def __init__(self):
        self.workshop_connection = None
        self.lab_connections = set()
        
    async def handle_workshop(self, websocket):
        """Handle workshop (server) connection"""
        logger.info(f"Workshop connected from {websocket.remote_address}")
        self.workshop_connection = websocket
        
        try:
            async for message in websocket:
                # Workshop sends acknowledgments back to lab
                for lab_conn in list(self.lab_connections):
                    try:
                        await lab_conn.send(message)
                        logger.debug(f"Forwarded ack from workshop to lab")
                    except Exception as e:
                        logger.error(f"Error sending to lab: {e}")
                        if lab_conn in self.lab_connections:
                            self.lab_connections.remove(lab_conn)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Workshop disconnected")
        except Exception as e:
            logger.error(f"Error in handle_workshop: {e}", exc_info=True)
        finally:
            self.workshop_connection = None
    
    async def handle_lab(self, websocket):
        """Handle lab (client) connection"""
        logger.info(f"Lab connected from {websocket.remote_address}")
        self.lab_connections.add(websocket)
        
        try:
            async for message in websocket:
                # Forward control data from lab to workshop
                if self.workshop_connection:
                    try:
                        await self.workshop_connection.send(message)
                        logger.debug(f"Forwarded message from lab to workshop")
                    except Exception as e:
                        logger.error(f"Error forwarding to workshop: {e}")
                        try:
                            await websocket.send(json.dumps({
                                'status': 'error',
                                'message': 'Workshop not connected'
                            }))
                        except:
                            pass
                else:
                    logger.warning("No workshop connected, sending error to lab")
                    try:
                        await websocket.send(json.dumps({
                            'status': 'error',
                            'message': 'Workshop not connected'
                        }))
                    except:
                        pass
        except websockets.exceptions.ConnectionClosed:
            logger.info("Lab disconnected")
        except Exception as e:
            logger.error(f"Error in handle_lab: {e}", exc_info=True)
        finally:
            if websocket in self.lab_connections:
                self.lab_connections.remove(websocket)
    
    async def handle_connection(self, websocket):
        """Route connections based on path"""
        path = websocket.request.path
        if path == "/workshop":
            await self.handle_workshop(websocket)
        elif path == "/lab":
            await self.handle_lab(websocket)
        else:
            logger.warning(f"Unknown path: {path}")
            await websocket.close()
    
    async def start(self, host="0.0.0.0", port=None):
        """Start the relay server"""
        if port is None:
            import os
            port = int(os.environ.get("PORT", 8080))
        
        logger.info(f"Starting relay server on {host}:{port}")
        logger.info("Workshop should connect to: ws://YOUR_DOMAIN/workshop")
        logger.info("Lab should connect to: ws://YOUR_DOMAIN/lab")
        
        async with websockets.serve(self.handle_connection, host, port):
            await asyncio.Future()  # Run forever


def main():
    relay = RelayServer()
    asyncio.run(relay.start())


if __name__ == "__main__":
    main()
