# config/settings.py
import os
import secrets
import logging

class Settings:
    """Configuration settings for metadata-resistant network"""
    
    # Server settings
    SERVER_HOST = "0.0.0.0"  # Listen on all interfaces
    SERVER_PORT = 5684       # Default CoAP over DTLS port
    
    # DTLS PSK Authentication
    # Generate a random PSK identity and key if not set
    PSK_IDENTITY = os.environ.get("PSK_IDENTITY", "metadata-resistant-network")
    PSK_KEY = os.environ.get("PSK_KEY", secrets.token_hex(16))  # 16 bytes = 128 bits
    
    # Traffic Obfuscation Settings
    # Random delay range in seconds
    MIN_DELAY = float(os.environ.get("MIN_DELAY", "0.05"))
    MAX_DELAY = float(os.environ.get("MAX_DELAY", "0.5"))
    
    # Padding settings
    PADDING_PROBABILITY = float(os.environ.get("PADDING_PROBABILITY", "0.7"))
    MIN_PADDING = int(os.environ.get("MIN_PADDING", "50"))
    MAX_PADDING = int(os.environ.get("MAX_PADDING", "500"))
    
    # Frequency hopping settings
    ENABLE_FREQUENCY_HOPPING = os.environ.get("ENABLE_FREQUENCY_HOPPING", "true").lower() == "true"
    MIN_HOP_INTERVAL = float(os.environ.get("MIN_HOP_INTERVAL", "30"))  # Seconds
    MAX_HOP_INTERVAL = float(os.environ.get("MAX_HOP_INTERVAL", "120"))  # Seconds
    
    # Fixed interval communication (to hide timing patterns)
    FIXED_INTERVAL = float(os.environ.get("FIXED_INTERVAL", "0"))  # 0 disables fixed interval
    MIN_JITTER = float(os.environ.get("MIN_JITTER", "0.1"))  # Seconds
    MAX_JITTER = float(os.environ.get("MAX_JITTER", "0.5"))  # Seconds
    
    # Dummy message probability for traffic analysis resistance
    DUMMY_MSG_PROBABILITY = float(os.environ.get("DUMMY_MSG_PROBABILITY", "0.2"))
    
    # Tor Integration
    USE_TOR = os.environ.get("USE_TOR", "false").lower() == "true"
    TOR_SOCKS_PORT = int(os.environ.get("TOR_SOCKS_PORT", "9050"))
    TOR_CONTROL_PORT = int(os.environ.get("TOR_CONTROL_PORT", "9051"))
    TOR_CONTROL_PASSWORD = os.environ.get("TOR_CONTROL_PASSWORD", "")
    USE_NEW_TOR_CIRCUIT = os.environ.get("USE_NEW_TOR_CIRCUIT", "true").lower() == "true"
    TOR_CIRCUIT_INTERVAL = float(os.environ.get("TOR_CIRCUIT_INTERVAL", "300"))  # 5 minutes
    
    # I2P Integration
    USE_I2P = os.environ.get("USE_I2P", "false").lower() == "true"
    I2P_HTTP_PORT = int(os.environ.get("I2P_HTTP_PORT", "4444"))
    I2P_SOCKS_PORT = int(os.environ.get("I2P_SOCKS_PORT", "4447"))
    
    def __init__(self):
        """Initialize settings and perform validation"""
        self._validate_settings()
        self._log_important_settings()
    
    def _validate_settings(self):
        """Validate settings to catch configuration errors early"""
        if self.MIN_DELAY >= self.MAX_DELAY:
            logging.warning("MIN_DELAY should be less than MAX_DELAY, adjusting...")
            self.MAX_DELAY = self.MIN_DELAY + 0.5
            
        if self.MIN_PADDING >= self.MAX_PADDING:
            logging.warning("MIN_PADDING should be less than MAX_PADDING, adjusting...")
            self.MAX_PADDING = self.MIN_PADDING + 100
            
        if self.MIN_HOP_INTERVAL >= self.MAX_HOP_INTERVAL:
            logging.warning("MIN_HOP_INTERVAL should be less than MAX_HOP_INTERVAL, adjusting...")
            self.MAX_HOP_INTERVAL = self.MIN_HOP_INTERVAL + 30
            
        if self.PADDING_PROBABILITY < 0 or self.PADDING_PROBABILITY > 1:
            logging.warning("PADDING_PROBABILITY should be between 0 and 1, adjusting...")
            self.PADDING_PROBABILITY = max(0, min(1, self.PADDING_PROBABILITY))
            
        if self.DUMMY_MSG_PROBABILITY < 0 or self.DUMMY_MSG_PROBABILITY > 1:
            logging.warning("DUMMY_MSG_PROBABILITY should be between 0 and 1, adjusting...")
            self.DUMMY_MSG_PROBABILITY = max(0, min(1, self.DUMMY_MSG_PROBABILITY))
    
    def _log_important_settings(self):
        """Log important settings for debugging"""
        logging.info("Metadata-Resistant Network Configuration:")
        logging.info(f"  Server Port: {self.SERVER_PORT}")
        logging.info(f"  PSK Identity: {self.PSK_IDENTITY}")
        logging.info(f"  Traffic Obfuscation: Padding Probability={self.PADDING_PROBABILITY}")
        logging.info(f"  Frequency Hopping: {'Enabled' if self.ENABLE_FREQUENCY_HOPPING else 'Disabled'}")
        
        if self.USE_TOR:
            logging.info(f"  Tor Integration: Enabled (SOCKS Port={self.TOR_SOCKS_PORT})")
        elif self.USE_I2P:
            logging.info(f"  I2P Integration: Enabled (SOCKS Port={self.I2P_SOCKS_PORT})")
        else:
            logging.info("  Anonymization: Disabled")

# Create a singleton instance
settings = Settings()

# Export all settings as module-level variables
for key, value in vars(settings).items():
    if not key.startswith('_'):
        globals()[key] = value