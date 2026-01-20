"""
Lab Relay Client - Connects to relay server to send control data
Runs on lab computer with CARLA
"""

import asyncio
import websockets
import json
import logging
from datetime import datetime
import ssl
import config

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LabRelayClient:
    def __init__(self, relay_uri):
        self.relay_uri = relay_uri
        self.websocket = None
        self.running = False
        self.latency_samples = []
        
    def get_carla_control_data(self):
        """Extract control data from CARLA simulation"""
        # TODO: Replace with actual CARLA integration
        import random
        throttle = random.uniform(0, 80)
        brake = random.uniform(0, 20)
        steering = random.uniform(-30, 30)
        
        return throttle, brake, steering
    
    async def connect(self):
        """Connect to relay server"""
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
                logger.info("[OK] Connected to relay server as lab")
                return True
                
            except Exception as e:
                logger.error(f"Connection failed: {str(e)}")
                logger.info(f"Retrying in {config.RECONNECT_DELAY} seconds...")
                await asyncio.sleep(config.RECONNECT_DELAY)
        
        return False
    
    async def send_control_data(self, throttle, brake, steering):
        """Send control data to relay server"""
        try:
            data = {
                'throttle': throttle,
                'brake': brake,
                'steering': steering,
                'timestamp': datetime.now().timestamp()
            }
            
            await self.websocket.send(json.dumps(data))
            
            try:
                response = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=config.CONNECTION_TIMEOUT
                )
                
                ack = json.loads(response)
                
                if ack.get('status') == 'ok':
                    latency = (datetime.now().timestamp() - data['timestamp']) * 1000
                    self.latency_samples.append(latency)
                    
                    if len(self.latency_samples) > 100:
                        self.latency_samples.pop(0)
                    
                    avg_latency = sum(self.latency_samples) / len(self.latency_samples)
                    
                    logger.debug(f"Sent: T={throttle:.1f} B={brake:.1f} S={steering:.1f} | Latency: {latency:.2f}ms (avg: {avg_latency:.2f}ms)")
                    return True
                else:
                    logger.warning(f"Server error: {ack.get('message')}")
                    return False
                    
            except asyncio.TimeoutError:
                logger.warning("Acknowledgment timeout")
                return False
                
        except Exception as e:
            logger.error(f"Error sending data: {str(e)}")
            return False
    
    async def run(self):
        """Main client loop"""
        self.running = True
        
        while self.running:
            if self.websocket is None:
                if not await self.connect():
                    break
            
            try:
                throttle, brake, steering = self.get_carla_control_data()
                
                success = await self.send_control_data(throttle, brake, steering)
                
                if not success:
                    logger.warning("Failed to send data, reconnecting...")
                    self.websocket = None
                    continue
                
                await asyncio.sleep(0.01)  # 100Hz
                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection closed, reconnecting...")
                self.websocket = None
                await asyncio.sleep(config.RECONNECT_DELAY)
                
            except KeyboardInterrupt:
                logger.info("Stopping client...")
                self.running = False
                break
                
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                await asyncio.sleep(1)
    
    def print_statistics(self):
        """Print connection statistics"""
        if self.latency_samples:
            avg = sum(self.latency_samples) / len(self.latency_samples)
            min_lat = min(self.latency_samples)
            max_lat = max(self.latency_samples)
            
            print("\n" + "=" * 60)
            print("LATENCY STATISTICS")
            print("=" * 60)
            print(f"Average: {avg:.2f}ms")
            print(f"Min: {min_lat:.2f}ms")
            print(f"Max: {max_lat:.2f}ms")
            print(f"Samples: {len(self.latency_samples)}")
            print("=" * 60)


def main():
    print("=" * 60)
    print("LAB RELAY CLIENT - Vehicle Control Sender")
    print("=" * 60)
    
    
    # Build relay URI
    protocol = "wss" if config.SERVER_PORT == 443 else "ws"
    if config.SERVER_PORT == 443:
        relay_uri = f"{protocol}://{config.WORKSHOP_IP}/lab"
    else:
        relay_uri = f"{protocol}://{config.WORKSHOP_IP}:{config.SERVER_PORT}/lab"
    
    print(f"Relay server: {relay_uri}")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")
    
    client = LabRelayClient(relay_uri)
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n\nStopping client...")
    finally:
        client.print_statistics()
        print("Client stopped")


if __name__ == "__main__":
    main()
