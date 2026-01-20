"""
Configuration file for Real-Time Vehicle Control Communication System
"""

# Network Configuration
SERVER_HOST = "0.0.0.0"  # Workshop server listens on all interfaces
SERVER_PORT = 443
WORKSHOP_IP = "vehicle-control-relay.onrender.com"  # localhost for same-computer testing

# Connection Settings
CONNECTION_TIMEOUT = 5  # seconds
RECONNECT_DELAY = 2  # seconds
PING_INTERVAL = 1  # seconds for keepalive

# Data Validation Ranges
THROTTLE_MIN = 0
THROTTLE_MAX = 100
BRAKE_MIN = 0
BRAKE_MAX = 100
STEERING_MIN = -180  # degrees
STEERING_MAX = 180   # degrees

# Safety Settings
MAX_COMMAND_AGE = 0.5  # seconds - commands older than this are considered stale
EMERGENCY_STOP_TIMEOUT = 1.0  # seconds - if no data received, trigger safety stop

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "vehicle_control.log"
