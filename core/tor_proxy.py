# core/tor_proxy.py
import logging
import socket
import asyncio
import socks
import stem
from stem.control import Controller
from stem import Signal
import time
import random

logger = logging.getLogger('tor_proxy')

class TorProxy:
    """
    Integration with Tor network for anonymous communication
    """
    def __init__(self, 
                 socks_port=9050, 
                 control_port=9051, 
                 control_password=None,
                 use_new_circuit=True,
                 circuit_change_interval=300):  # 5 minutes default
        """
        Initialize Tor proxy settings
        
        Args:
            socks_port: Tor SOCKS proxy port
            control_port: Tor control port for API access
            control_password: Password for Tor control port
            use_new_circuit: Whether to periodically change circuits
            circuit_change_interval: Seconds between circuit changes
        """
        self.socks_port = socks_port
        self.control_port = control_port
        self.control_password = control_password
        self.use_new_circuit = use_new_circuit
        self.circuit_change_interval = circuit_change_interval
        self.last_circuit_change = time.time()
        self.active = False
        
    def configure_socket(self, socket_obj):
        """Configure a socket to use Tor SOCKS proxy"""
        if not self.active:
            logger.warning("Tor proxy not active, socket not configured")
            return socket_obj
            
        # Configure socket to use SOCKS proxy
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
        socket.socket = socks.socksocket
        logger.info(f"Socket configured to use Tor SOCKS proxy on port {self.socks_port}")
        return socket_obj
        
    async def start(self):
        """Start and check Tor proxy connection"""
        try:
            # Check if Tor is running
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', self.socks_port))
            sock.close()
            
            if result != 0:
                logger.error(f"Tor proxy not running on port {self.socks_port}")
                return False
                
            # Test connection through Tor
            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
            socket.socket = socks.socksocket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            try:
                s.connect(("check.torproject.org", 443))
                logger.info("Successfully connected through Tor proxy")
                self.active = True
            except Exception as e:
                logger.error(f"Failed to connect through Tor: {e}")
                return False
            finally:
                s.close()
                
            # Start background task for circuit rotation if enabled
            if self.use_new_circuit:
                asyncio.create_task(self._rotate_circuits())
                
            return True
                
        except Exception as e:
            logger.error(f"Error setting up Tor proxy: {e}")
            return False
    
    async def _rotate_circuits(self):
        """Background task to periodically change Tor circuits"""
        while self.active and self.use_new_circuit:
            current_time = time.time()
            
            # Add some randomness to the interval (±20%)
            jitter = self.circuit_change_interval * 0.2
            actual_interval = self.circuit_change_interval + random.uniform(-jitter, jitter)
            
            # Check if it's time to change circuit
            if current_time - self.last_circuit_change >= actual_interval:
                await self.new_circuit()
                self.last_circuit_change = current_time
                
            # Check again after a delay
            await asyncio.sleep(min(60, actual_interval / 10))
    
    async def new_circuit(self):
        """Request a new Tor circuit to change path and exit node"""
        if not self.active:
            return False
            
        try:
            # Connect to Tor controller API
            with Controller.from_port(port=self.control_port) as controller:
                if self.control_password:
                    controller.authenticate(password=self.control_password)
                else:
                    controller.authenticate()
                    
                # Signal for new circuit
                controller.signal(Signal.NEWNYM)
                logger.info("Requested new Tor circuit")
                
                # Wait a moment for the change to take effect
                await asyncio.sleep(1)
                return True
                
        except stem.SocketError:
            logger.error(f"Error connecting to Tor control port {self.control_port}")
            return False
        except stem.connection.AuthenticationFailure:
            logger.error("Failed to authenticate with Tor controller")
            return False
        except Exception as e:
            logger.error(f"Error requesting new Tor circuit: {e}")
            return False
    
    async def stop(self):
        """Stop Tor proxy usage"""
        self.active = False
        logger.info("Tor proxy integration stopped")


class I2PProxy:
    """
    Integration with I2P network as an alternative to Tor
    """
    def __init__(self, http_proxy_port=4444, socks_proxy_port=4447):
        """
        Initialize I2P proxy settings
        
        Args:
            http_proxy_port: I2P HTTP proxy port
            socks_proxy_port: I2P SOCKS proxy port
        """
        self.http_proxy_port = http_proxy_port
        self.socks_proxy_port = socks_proxy_port
        self.active = False
        
    async def start(self):
        """Start and check I2P proxy connection"""
        try:
            # Check if I2P is running by testing SOCKS proxy
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', self.socks_proxy_port))
            sock.close()
            
            if result != 0:
                logger.error(f"I2P SOCKS proxy not running on port {self.socks_proxy_port}")
                return False
            
            # Configure system for I2P proxy
            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", self.socks_proxy_port)
            socket.socket = socks.socksocket
            
            self.active = True
            logger.info("I2P proxy integration active")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up I2P proxy: {e}")
            return False
    
    async def stop(self):
        """Stop I2P proxy usage"""
        self.active = False
        # Reset socket back to default (non-proxied)
        socket.socket = socket._socketobject
        logger.info("I2P proxy integration stopped")