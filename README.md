# Protocol-Aware Cloud Relay Server

A high-performance WebSocket relay server designed for real-time communication between distributed clients (e.g., Lab controls and Workshop hardware). Deployed on Render with support for multiple communication patterns.

## Deployed Server
- **URL:** `https://webrelay-server-lqrn.onrender.com`
- **Health Check:** `https://webrelay-server-lqrn.onrender.com/health`

---

## Setup
1. **Create Virtual Environment:**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Connection:**
   Update `config.py` with your server domain.

---

## Protocol Usage Guide (`lab_relay_client.py`)

### 1. Push / Pull Protocol (Queue)
Messages are sent to a queue and held until a consumer pulls them.

| Role                    | Start Command                                                     | Action Inside App                        |
| :---------------------- | :---------------------------------------------------------------- | :--------------------------------------- |
| **Sender** (Producer)   | `python lab_relay_client.py --protocol push_pull --role producer` | Type text and press **Enter** to "push". |
| **Receiver** (Consumer) | `python lab_relay_client.py --protocol push_pull --role consumer` | Type `/pull` to fetch the message.       |

### 2. Request / Response Protocol (Ticket System)
Synchronous-style messaging where responders reply to specific Request IDs.

| Role                     | Start Command                                                             | Action Inside App                         |
| :----------------------- | :------------------------------------------------------------------------ | :---------------------------------------- |
| **Sender** (Requester)   | `python lab_relay_client.py --protocol request_response --role requester` | Type text and press **Enter** to request. |
| **Receiver** (Responder) | `python lab_relay_client.py --protocol request_response --role responder` | Type `/reply <ID> <message>`              |

### 3. Exclusive Pair Protocol (Direct Chat)
Direct 1-to-1 connection between two peers in the same room.

| Side       | Start Command                                                                   | Action Inside App      |
| :--------- | :------------------------------------------------------------------------------ | :--------------------- |
| **Peer A** | `python lab_relay_client.py --protocol exclusive_pair --role peer --name Alice` | Type to chat directly. |
| **Peer B** | `python lab_relay_client.py --protocol exclusive_pair --role peer --name Bob`   | Type to chat directly. |

---

## Server Architecture
The server is built with `aiohttp` and supports:
- `/workshop` & `/lab`: Legacy vehicle control relay.
- `/protocol`: Multi-mode protocol demo.
- Standardized heartbeat (20s) and health monitoring.

## Common Commands
- `/help` : Show role-specific help.
- `/quit` : Exit the client.

