"""Module for amt-8000 communication."""

import socket
import logging
from typing import Dict, Any # Import for type hinting

LOGGER = logging.getLogger(__name__)

timeout = 2  # Set the timeout to 2 seconds

dst_id = [0x00, 0x00]
our_id = [0x8F, 0xFF]
commands = {
    "auth": [0xF0, 0xF0],
    "status": [0x0B, 0x4A],
    "arm_disarm": [0x40, 0x1e],
    "panic": [0x40, 0x1a],
    "paired_sensors": [0x0B, 0x01] # ADDED: Command for paired sensors
}

# Constantes para el procesamiento de zonas
ZONE_PAYLOAD_OFFSET = 64  # The first zone byte within the payload (from the fork)
MAX_ZONES = 64 # Maximum number of zones that can be read (8 bytes * 8 bits)

def split_into_octets(n):
    """Splits an integer into high and low bytes."""
    if 0 <= n <= 0xFFFF:
        high_byte = (n >> 8) & 0xFF
        low_byte = n & 0xFF
        return [high_byte, low_byte]
    else:
        raise ValueError("Número fora do intervalo (0 a 65535)")

def calculate_checksum(buffer):
    """Calculate a checksum for a given array of bytes."""
    checksum = 0
    for value in buffer:
        checksum ^= value
    checksum ^= 0xFF
    checksum &= 0xFF
    return checksum

def merge_octets(buf):
    """Merge octets."""
    return buf[0] * 256 + buf[1]

def battery_status_for(resp):
    """Retrieve the battery status."""
    # El payload debe tener al menos 135 bytes para que el índice 134 sea válido
    if len(resp) <= 134:
        LOGGER.debug("Payload too short for battery status. Length: %d", len(resp))
        return "unknown"
    batt = resp[134]
    if batt == 0x01:
        return "dead"
    if batt == 0x02:
        return "low"
    if batt == 0x03:
        return "middle"
    if batt == 0x04:
        return "full"
    LOGGER.debug("Unknown battery status code: 0x%02x", batt)
    return "unknown"

def get_status(payload):
    """Retrieve the current status from a given array of bytes."""
    # El payload debe tener al menos 21 bytes para que el índice 20 sea válido
    if len(payload) <= 20:
        LOGGER.debug("Payload too short for general status. Length: %d", len(payload))
        return "unknown"
    status = (payload[20] >> 5) & 0x03
    if status == 0x00:
        return "disarmed"
    if status == 0x01:
        return "partial_armed"
    if status == 0x03:
        return "armed_away"
    LOGGER.debug("Unknown arming status code: 0x%02x", status)
    return "unknown"

# --- build_status mejorado para manejar el payload completo y robustez ---
def build_status(data: bytearray) -> Dict[str, Any]: # Added type hints for clarity
    """Build the amt-8000 status from a given array of bytes, including zone status."""
    if len(data) < 8:
        LOGGER.error("Received status data is too short (less than 8 bytes). Data: %s", data.hex())
        return {
            "model": "Unknown",
            "version": "Unknown",
            "status": "unknown",
            "zonesFiring": False,
            "zonesClosed": False,
            "siren": False,
            "batteryStatus": "unknown",
            "tamper": False,
            "zones": {} # Added zones to initial return
        }

    # El campo de longitud del paquete se encuentra en los bytes 4 y 5
    length_bytes = data[4:6]
    if len(length_bytes) < 2:
        LOGGER.error("Length bytes are missing or insufficient in status data. Data: %s", data.hex())
        return {
            "model": "Unknown",
            "version": "Unknown",
            "status": "unknown",
            "zonesFiring": False,
            "zonesClosed": False,
            "siren": False,
            "batteryStatus": "unknown",
            "tamper": False,
            "zones": {} # Added zones to initial return
        }

    expected_payload_length = merge_octets(data[4:6])

    if len(data) < 8 + expected_payload_length:
        LOGGER.warning("Received data is shorter than indicated length. Expected: %d, Received: %d. Data: %s",
                       8 + expected_payload_length, len(data), data.hex())
        payload = data[8:] # Tomamos lo que esté disponible
    else:
        payload = data[8 : 8 + expected_payload_length]

    LOGGER.debug("Raw payload for status: %s", payload.hex())

    status_data = {}

    # Decodificación del modelo
    status_data["model"] = "Unknown"
    if len(payload) > 0:
        status_data["model"] = "AMT-8000" if payload[0] == 1 else "Unknown"

    # Decodificación de la versión
    status_data["version"] = "Unknown"
    if len(payload) > 3:
        status_data["version"] = f"{payload[1]}.{payload[2]}.{payload[3]}"
    
    # Decodificación del estado general y bits de zonas/sirena
    status_data["status"] = "unknown"
    status_data["zonesFiring"] = False
    status_data["zonesClosed"] = False
    status_data["siren"] = False
    if len(payload) > 20:
        status_data["status"] = get_status(payload)
        status_data["zonesFiring"] = (payload[20] & 0x8) > 0
        status_data["zonesClosed"] = (payload[20] & 0x4) > 0
        status_data["siren"] = (payload[20] & 0x2) > 0
    else:
        LOGGER.debug("Payload too short for full status bits. Length: %d", len(payload))

    # Decodificación del estado de la batería
    status_data["batteryStatus"] = battery_status_for(payload) # Use payload here

    # Decodificación del tamper
    status_data["tamper"] = False
    if len(payload) > 71:
        status_data["tamper"] = (payload[71] & (1 << 0x01)) > 0
    else:
        LOGGER.debug("Payload too short for tamper status. Length: %d", len(payload))

    # ADDED: Individual zone status processing
    zones = {}
    zones_data_start_payload_index = ZONE_PAYLOAD_OFFSET # This is 64 in the payload
    for byte_index in range(8): # Assuming 8 bytes for 64 zones
        current_byte_index = zones_data_start_payload_index + byte_index
        if current_byte_index < len(payload): # Ensure we don't go out of bounds
            byte_value = payload[current_byte_index]
            for bit in range(8):
                zone_number = (byte_index * 8) + bit + 1
                zone_open = (byte_value & (1 << bit)) == 0 # If bit is 0, zone is OPEN
                zones[str(zone_number)] = "open" if zone_open else "closed"
        else:
            LOGGER.warning(f"Datos de zonas incompletos a partir del byte {current_byte_index} del payload.")
            break # Exit if no more data

    status_data["zones"] = zones # Add individual zone states

    LOGGER.debug("Decoded status: %s", status_data)
    return status_data


class CommunicationError(Exception):
    """Exception raised for communication error."""

    def __init__(self, message="Communication error"):
        """Initialize the error."""
        self.message = message
        super().__init__(self.message)


class AuthError(Exception):
    """Exception raised for authentication error."""

    def __init__(self, message="Authentication Error"):
        """Initialize the error."""
        self.message = message
        super().__init__(self.message)


class Client:
    """Client to communicate with amt-8000."""

    def __init__(self, host, port, device_type=1, software_version=0x10):
        """Initialize the client."""
        self.host = host
        self.port = port
        self.device_type = device_type
        self.software_version = software_version
        self.client = None

    def close(self):
        """Close a connection."""
        if self.client is None:
            LOGGER.warning("Attempted to close a non-existent client connection.")
            return

        try:
            self.client.shutdown(socket.SHUT_RDWR)
            self.client.close()
        except OSError as e:
            LOGGER.debug("Error closing socket: %s", e)
        finally:
            self.client = None

    def connect(self):
        """Create a new connection."""
        if self.client:
            self.close() # Cierra la conexión existente antes de intentar una nueva

        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(timeout)
        LOGGER.debug("Connecting to %s:%d", self.host, self.port)
        try:
            self.client.connect((self.host, self.port))
            LOGGER.debug("Connection established.")
        except socket.timeout:
            raise CommunicationError(f"Connection timed out to {self.host}:{self.port}")
        except ConnectionRefusedError:
            raise CommunicationError(f"Connection refused by {self.host}:{self.port}")
        except OSError as e:
            raise CommunicationError(f"OS error connecting to {self.host}:{self.port}: {e}")

    def auth(self, password):
        """Create a authentication for the current connection."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect first.")

        pass_array = []
        for char in password:
            if len(password) != 6 or not char.isdigit():
                raise CommunicationError(
                    "Cannot parse password, only 6 integers long are accepted"
                )
            pass_array.append(int(char))

        length = [0x00, 0x0a] # THIS IS FROM YOUR UPLOADED CLIENT.PY - ENSURE IT'S CORRECT FOR YOUR PANEL
        data = (
            dst_id
            + our_id
            + length
            + commands["auth"]
            + [self.device_type]
            + pass_array
            + [self.software_version]
        )

        cs = calculate_checksum(data)
        payload = bytes(data + [cs])

        LOGGER.debug("Sending authentication: %s", payload.hex())
        try:
            self.client.send(payload)
            return_data = bytearray(self.client.recv(1024))
        except socket.timeout:
            raise CommunicationError("Authentication response timed out.")
        except OSError as e:
            raise CommunicationError(f"OS error during authentication: {e}")

        LOGGER.debug("Raw authentication response: %s", return_data.hex())

        if len(return_data) < 9:
            raise CommunicationError(f"Authentication response too short. Length: {len(return_data)}. Raw: {return_data.hex()}")

        result = return_data[8:9][0]

        if result == 0:
            LOGGER.info("Authentication successful.")
            return True
        if result == 1:
            raise AuthError("Invalid password")
        if result == 2:
            raise AuthError("Incorrect software version")
        if result == 3:
            raise AuthError("Alarm panel will call back")
        if result == 4:
            raise AuthError("Waiting for user permission")
        raise CommunicationError(f"Unknown payload response for authentication: 0x{result:02x}")

    def status(self):
        """Return the current status."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect first.")

        length = [0x00, 0x02]
        status_data = dst_id + our_id + length + commands["status"]
        cs = calculate_checksum(status_data)
        payload = bytes(status_data + [cs])

        LOGGER.debug("Sending status command: %s", payload.hex())
        try:
            self.client.send(payload)
            # Recibe toda la respuesta esperada en una sola llamada
            return_data = bytearray(self.client.recv(1024))
        except socket.timeout:
            raise CommunicationError("Status command response timed out.")
        except OSError as e:
            raise CommunicationError(f"OS error during status command: {e}")

        LOGGER.debug("Raw status response (full): %s", return_data.hex())
        status = build_status(return_data)
        return status

    def arm_system(self, partition):
        """Arm the system for a given partition."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect first.")

        # La integración original usa 0xFF para partition 0 (master)
        if partition == 0:
            partition = 0xFF

        length = [0x00, 0x04]
        arm_data = dst_id + our_id + length + commands["arm_disarm"] + [ partition, 0x01 ] # 0x01 for arm
        cs = calculate_checksum(arm_data)
        payload = bytes(arm_data + [cs])

        LOGGER.debug("Sending arm command: %s", payload.hex())
        try:
            self.client.send(payload)
            return_data = bytearray(self.client.recv(1024))
        except socket.timeout:
            raise CommunicationError("Arm command response timed out.")
        except OSError as e:
            raise CommunicationError(f"OS error during arm command: {e}")

        LOGGER.debug("Raw arm response: %s", return_data.hex())
        # La integración original verifica el byte 8 para 0x91
        if len(return_data) > 8 and return_data[8] == 0x91:
            LOGGER.info("System armed successfully.")
            return 'armed'
        
        LOGGER.warning("Arm command failed. Response: %s", return_data.hex())
        return 'not_armed'

    def disarm_system(self, partition):
        """Disarm the system for a given partition."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect first.")

        if partition == 0:
            partition = 0xFF

        length = [0x00, 0x04]
        disarm_data = dst_id + our_id + length + commands["arm_disarm"] + [ partition, 0x00 ] # 0x00 for disarm
        cs = calculate_checksum(disarm_data)
        payload = bytes(disarm_data + [cs])

        LOGGER.debug("Sending disarm command: %s", payload.hex())
        try:
            self.client.send(payload)
            return_data = bytearray(self.client.recv(1024))
        except socket.timeout:
            raise CommunicationError("Disarm command response timed out.")
        except OSError as e:
            raise CommunicationError(f"OS error during disarm command: {e}")

        LOGGER.debug("Raw disarm response: %s", return_data.hex())
        if len(return_data) > 8 and return_data[8] == 0x91:
            LOGGER.info("System disarmed successfully.")
            return 'disarmed'
        
        LOGGER.warning("Disarm command failed. Response: %s", return_data.hex())
        return 'not_disarmed'

    def panic(self, panic_type):
        """Trigger a panic alarm."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect first.")

        length = [0x00, 0x03]
        panic_data = dst_id + our_id + length + commands["panic"] +[ panic_type ]
        cs = calculate_checksum(panic_data)
        payload = bytes(panic_data + [cs])

        LOGGER.debug("Sending panic command: %s", payload.hex())
        try:
            self.client.send(payload)
            return_data = bytearray(self.client.recv(1024))
        except socket.timeout:
            raise CommunicationError("Panic command response timed out.")
        except OSError as e:
            raise CommunicationError(f"OS error during panic command: {e}")

        LOGGER.debug("Raw panic response: %s", return_data.hex())
        # La integración original verifica el byte 7 para 0xfe
        if len(return_data) > 7 and return_data[7] == 0xfe:
            LOGGER.info("Panic alarm triggered.")
            return 'triggered'
        
        LOGGER.warning("Panic command failed. Response: %s", return_data.hex())
        return 'not_triggered'
    
    # ADDED: Method to get paired sensors
    def get_paired_sensors(self) -> Dict[str, bool]:
        """Get the list of paired sensors from the alarm panel."""
        if self.client is None:
            raise CommunicationError("Client not connected. Call Client.connect")

        length = [0x00, 0x02] # Command is 2 bytes
        sensors_data = dst_id + our_id + length + commands["paired_sensors"]
        cs = calculate_checksum(sensors_data)
        payload = bytes(sensors_data + [cs])

        LOGGER.debug("Sending paired sensors command: %s", payload.hex())
        return_data = bytearray()
        try:
            self.client.send(payload)
            data = self.client.recv(1024) # Read the response
            return_data.extend(data)
            LOGGER.debug("Raw paired sensors response: %s", return_data.hex())
        except socket.timeout:
            raise CommunicationError("Paired sensors command response timed out.")
        except OSError as e:
            raise CommunicationError(f"OS error during paired sensors command: {e}")

        # Check for error response first (0xfd at index 8, if panel sends it)
        if len(return_data) > 8 and return_data[8] == 0xfd:
            LOGGER.warning("Panel returned error for get_paired_sensors command (0xfd).")
            return {} # Return empty if command failed

        # The response starts in the byte 8 (after header)
        # Each byte represents 8 zones (1 bit per zone)
        paired_zones = {}
        try:
            # Skip header (8 bytes) and read the 8 bytes of zone data
            for byte_index in range(8):  # 8 bytes = 64 zones
                # Ensure we have enough data in return_data for the current byte
                if len(return_data) > 8 + byte_index:
                    byte_value = return_data[8 + byte_index]
                    for bit in range(8):
                        zone_number = (byte_index * 8) + bit + 1
                        # If the bit is 1, the zone is paired
                        if (byte_value & (1 << bit)) > 0:
                            paired_zones[str(zone_number)] = True
                else:
                    LOGGER.warning(f"Datos de paired zones incompletos en el byte {byte_index} del payload esperado.")
                    break # Exit if no more data

        except Exception as e:
            LOGGER.error(f"Error procesando datos de sensores emparejados: {e}", exc_info=True)
            return {} # Return an empty dictionary in case of error

        return paired_zones
