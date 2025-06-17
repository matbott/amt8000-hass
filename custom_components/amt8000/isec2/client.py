# isec2/client.py

import socket
import logging

LOGGER = logging.getLogger(__name__)

timeout = 2  # Set the timeout to 2 seconds

dst_id = [0x00, 0x00]
our_id = [0x8F, 0xFF]
commands = {
    "auth": [0xF0, 0xF0],
    "status": [0x0B, 0x4A],
    "arm_disarm": [0x40, 0x1e],
    "panic": [0x40, 0x1a]
}

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

# NUEVA FUNCIÓN: Obtener estado de las zonas
def get_zones_status_from_payload(payload: bytearray, num_zones: int = 64) -> list[bool]:
    """
    Decodes the zone status from the payload.
    The zone status bytes start at index 22 in the status payload.
    Each bit represents a zone (0 = closed, 1 = open/faulted).
    """
    zones_status = [False] * num_zones
    # Los bytes de estado de las zonas van del índice 22 al 29 para 64 zonas.
    # Cada byte contiene 8 zonas.
    # El fork de Fabiolopez90 usa los bytes 22 a 29.
    # Byte 22: Zonas 1-8
    # Byte 23: Zonas 9-16
    # ...
    # Byte 29: Zonas 57-64

    # Asegurarse de que el payload tenga al menos los bytes necesarios para las zonas
    # El byte 22 es para la Zona 1, hasta el byte 22 + (num_zones / 8) - 1
    # Por ejemplo, para 64 zonas, se necesitan (64/8) = 8 bytes, desde el índice 22 hasta el 29 (inclusive).
    required_bytes_for_zones = (num_zones + 7) // 8 # Redondeo hacia arriba para bytes
    
    if len(payload) < 22 + required_bytes_for_zones:
        LOGGER.warning(f"Payload too short to decode all {num_zones} zones. Required at least {22 + required_bytes_for_zones} bytes, got {len(payload)}.")
        # Decodificar solo las zonas para las que hay datos
        bytes_to_process = payload[22:]
    else:
        bytes_to_process = payload[22 : 22 + required_bytes_for_zones]

    zone_index = 0
    for byte_val in bytes_to_process:
        for bit_index in range(8):
            if zone_index < num_zones:
                # Si el bit es 1, la zona está abierta (faulted). Si es 0, está cerrada.
                zones_status[zone_index] = bool(byte_val & (1 << bit_index))
                zone_index += 1
            else:
                break # Ya decodificamos todas las zonas solicitadas
        if zone_index >= num_zones:
            break

    LOGGER.debug(f"Decoded zones status: {zones_status}")
    return zones_status


# --- build_status mejorado para manejar el payload completo y robustez ---
def build_status(data):
    """Build the amt-8000 status from a given array of bytes."""
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
            "zones": [False] * 64, # Inicializar con 64 zonas cerradas
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
            "zones": [False] * 64, # Inicializar con 64 zonas cerradas
        }

    expected_payload_length = merge_octets(data[4:6])

    if len(data) < 8 + expected_payload_length:
        LOGGER.warning("Received data is shorter than indicated length. Expected: %d, Received: %d. Data: %s",
                       8 + expected_payload_length, len(data), data.hex())
        payload = data[8:]
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
    status_data["batteryStatus"] = battery_status_for(payload)

    # Decodificación del tamper
    status_data["tamper"] = False
    if len(payload) > 71:
        status_data["tamper"] = (payload[71] & (1 << 0x01)) > 0
    else:
        LOGGER.debug("Payload too short for tamper status. Length: %d", len(payload))

    # AÑADIR DECODIFICACIÓN DE ZONAS AQUÍ
    status_data["zones"] = get_zones_status_from_payload(payload)

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
            self.close()

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

        length = [0x00, 0x0a]
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

        if partition == 0:
            partition = 0xFF

        length = [0x00, 0x04]
        arm_data = dst_id + our_id + length + commands["arm_disarm"] + [ partition, 0x01 ]
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
        arm_data = dst_id + our_id + length + commands["arm_disarm"] + [ partition, 0x00 ]
        cs = calculate_checksum(arm_data)
        payload = bytes(arm_data + [cs])

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
        if len(return_data) > 7 and return_data[7] == 0xfe:
            LOGGER.info("Panic alarm triggered.")
            return 'triggered'
        
        LOGGER.warning("Panic command failed. Response: %s", return_data.hex())
        return 'not_triggered'
