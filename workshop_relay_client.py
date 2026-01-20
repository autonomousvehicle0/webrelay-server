"""
Workshop Relay Client - Connects to relay server instead of listening directly
Runs on workshop computer
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
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WorkshopRelayClient:
    def __init__(self, relay_uri):
        self.relay_uri = relay_uri
        self.websocket = None
        self.running = False
        self.last_command_time = None
        
    def validate_control_data(self, data):
        """Validate incoming control data"""
        try:
            throttle = data.get('throttle')
            brake = data.get('brake')
            steering = data.get('steering')
            
            if throttle is None or brake is None or steering is None:
                return False, "Missing required fields"
            
            if not (config.THROTTLE_MIN <= throttle <= config.THROTTLE_MAX):
                return False, f"Throttle out of range: {throttle}"
            
            if not (config.BRAKE_MIN <= brake <= config.BRAKE_MAX):
                return False, f"Brake out of range: {brake}"
            
            if not (config.STEERING_MIN <= steering <= config.STEERING_MAX):
                return False, f"Steering out of range: {steering}"
            
            return True, "Valid"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def apply_to_hardware(self, throttle, brake, steering):
        """Interface to apply control commands to actual hardware"""
        logger.info(f"HARDWARE OUTPUT -> Throttle: {throttle:.1f}%, Brake: {brake:.1f}%, Steering: {steering:.1f}°")
        
        # TODO: Replace with your hardware interface
        # Example: serial communication, CAN bus, etc.
    
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
                logger.info("[OK] Connected to relay server as workshop")
                return True
                
            except Exception as e:
                logger.error(f"Connection failed: {str(e)}")
                logger.info(f"Retrying in {config.RECONNECT_DELAY} seconds...")
                await asyncio.sleep(config.RECONNECT_DELAY)
        
        return False
    
    async def handle_messages(self):
        """Handle incoming messages from relay"""
        try:
            async for message in self.websocket:
                receive_time = datetime.now()
                
                try:
                    data = json.loads(message)
                    
                    # Extract timestamp if present
                    sent_time = data.get('timestamp')
                    if sent_time:
                        latency = (receive_time.timestamp() - sent_time) * 1000
                        logger.debug(f"Latency: {latency:.2f}ms")
                    
                    # Validate data
                    valid, msg = self.validate_control_data(data)
                    if not valid:
                        logger.warning(f"Invalid data: {msg}")
                        await self.websocket.send(json.dumps({
                            'status': 'error',
                            'message': msg
                        }))
                        continue
                    
                    # Extract control values
                    throttle = data['throttle']
                    brake = data['brake']
                    steering = data['steering']
                    
                    # Apply to hardware
                    self.apply_to_hardware(throttle, brake, steering)
                    
                    # Update last command time
                    self.last_command_time = receive_time
                    
                    # Send acknowledgment
                    await self.websocket.send(json.dumps({
                        'status': 'ok',
                        'timestamp': receive_time.timestamp()
                    }))
                    
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection to relay closed")
    
    async def safety_monitor(self):
        """Monitor for connection timeout"""
        while self.running:
            await asyncio.sleep(0.1)
            
            if self.last_command_time:
                time_since_last = (datetime.now() - self.last_command_time).total_seconds()
                
                if time_since_last > config.EMERGENCY_STOP_TIMEOUT:
                    logger.warning("SAFETY TIMEOUT - No commands received, applying emergency stop")
                    self.apply_to_hardware(0, 100, 0)
                    self.last_command_time = None
    
    async def run(self):
        """Main run loop"""
        self.running = True
        
        # Start safety monitor
        asyncio.create_task(self.safety_monitor())
        
        while self.running:
            if not await self.connect():
                break
            
            try:
                await self.handle_messages()
            except Exception as e:
                logger.error(f"Error: {str(e)}")
            
            logger.info("Reconnecting...")
            await asyncio.sleep(config.RECONNECT_DELAY)


def main():
    print("=" * 60)
    print("WORKSHOP RELAY CLIENT - Vehicle Control Receiver")
    print("=" * 60)
    
    
    # Build relay URI
    protocol = "wss" if config.SERVER_PORT == 443 else "ws"
    if config.SERVER_PORT == 443:
        relay_uri = f"{protocol}://{config.WORKSHOP_IP}/workshop"
    else:
        relay_uri = f"{protocol}://{config.WORKSHOP_IP}:{config.SERVER_PORT}/workshop"
    
    print(f"Relay server: {relay_uri}")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")
    
    client = WorkshopRelayClient(relay_uri)
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        print("\nStopped")


if __name__ == "__main__":
    main()
