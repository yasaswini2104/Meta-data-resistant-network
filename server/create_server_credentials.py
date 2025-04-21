from aiocoap.credentials import CredentialsMap
import logging

logger = logging.getLogger(__name__)

def create_server_credentials(psk_identity: str, psk_key: str) -> CredentialsMap:
    """
    Create DTLS server credentials with PSK authentication
    
    Args:
        psk_identity: The Pre-Shared Key identity
        psk_key: The Pre-Shared Key in hex format
    
    Returns:
        CredentialsMap object containing the credentials
    """
    try:
        credentials = CredentialsMap()
        if isinstance(psk_key, str):
            if psk_key.startswith('0x'):
                psk_key = bytes.fromhex(psk_key[2:])
            else:
                psk_key = bytes.fromhex(psk_key)
        credentials[psk_identity] = psk_key
        logger.info(f"Created server credentials map with PSK identity: {psk_identity}")
        return credentials
    except Exception as e:
        logger.error(f"Failed to create server credentials map: {e}")
        raise