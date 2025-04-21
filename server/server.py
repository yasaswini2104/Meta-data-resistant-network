import asyncio
import logging
import socket
import time
import os
import sys
from pathlib import Path
import random

# Add project root to path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

from aiocoap import resource, Context, Message
import aiocoap
from aiocoap.credentials import CredentialsMap

from core.encryption import DTLSEncryption, MetadataProtection
from core.obfuscation import TrafficObfuscator, TimingObfuscator
from core.tor_proxy import TorProxy
from config.settings import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("metadata-resistant-server")

class PrivacyEnhancedResource(resource.Resource):
    """
    Resource that handles both GET and POST requests with privacy-enhancing features.
    """
    def __init__(self, obfuscator, timing_obfuscator, metadata_protection):
        super().__init__()
        # Store messages for broadcasting
        self.messages = []
        self.clients = set()
        # Privacy enhancing components
        self.obfuscator = obfuscator
        self.timing_obfuscator = timing_obfuscator
        self.metadata_protection = metadata_protection

    def get_client_info(self, request):
        """Safely extract client information from request object"""
        try:
            # First try the direct attribute
            if hasattr(request.remote, 'sockaddr'):
                return request.remote.sockaddr
            # Then try accessing address directly
            elif hasattr(request.remote, 'address'):
                return request.remote.address
            # If all else fails, return string representation
            else:
                return str(request.remote)
        except Exception as e:
            logger.error(f"Error getting client info: {e}")
            return "unknown-client"

    async def render_get(self, request):
        try:
            # Apply random delay to obscure timing
            await self.obfuscator.apply_random_delay()
            
            client_info = self.get_client_info(request)
            # Protect the client info in logs
            masked_info = f"client-{hash(str(client_info)) % 10000}"
            logger.info(f"Received GET request from: {masked_info}")
            
            # Add client to known clients - use as string if needed
            self.clients.add(client_info if isinstance(client_info, tuple) else (str(client_info), 0))
            
            # Create payload
            if self.messages:
                response_text = "\n".join(self.messages)
                payload = f"Welcome to Metadata-Resistant Network!\nPrevious messages:\n{response_text}".encode()
            else:
                payload = b"Welcome to Metadata-Resistant Network! No previous messages."
            
            # Apply padding and size normalization for traffic analysis resistance
            payload = self.obfuscator.add_padding(payload)
            payload = self.obfuscator.normalize_message_size(payload)
            
            # Create response message
            response = Message(payload=payload)
            
            # Wait for next interval if using fixed interval timing
            await self.timing_obfuscator.wait_for_next_interval()
            
            return response
            
        except Exception as e:
            logger.error(f"Error in GET handler: {e}")
            return Message(payload=f"Error: {str(e)}".encode())

    async def render_post(self, request):
        try:
            # Apply random delay to obscure timing
            await self.obfuscator.apply_random_delay()
            
            # Process the incoming message
            message_bytes = request.payload
            
            # Remove any obfuscation
            message_bytes = self.obfuscator.remove_padding(message_bytes)
            message_bytes = self.obfuscator.denormalize_message_size(message_bytes)
            message_bytes = self.timing_obfuscator.remove_dummy_marker(message_bytes)
            
            # Skip processing if it's a dummy message
            if message_bytes is None:
                logger.debug("Received dummy message, discarding")
                return Message(payload=b"Message received")
                
            # Process actual message
            try:
                message = message_bytes.decode()
            except UnicodeDecodeError:
                logger.error("Received undecodable message")
                return Message(payload=b"Error: Invalid message encoding")
                
            client_info = self.get_client_info(request)
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            
            # Format client info for display (anonymized)
            client_display = f"User-{hash(str(client_info)) % 1000}"
            
            # Add client to known clients
            self.clients.add(client_info if isinstance(client_info, tuple) else (str(client_info), 0))
            
            formatted_message = f"[{timestamp}] {client_display}: {message}"
            self.messages.append(formatted_message)
            
            logger.info(f"Received POST: message from {client_display}")
            
            # Create response
            payload = f"Message received: {message}".encode()
            payload = self.obfuscator.add_padding(payload)
            
            # Wait for next interval if using fixed interval timing
            await self.timing_obfuscator.wait_for_next_interval()
            
            return Message(payload=payload)
            
        except Exception as e:
            logger.error(f"Error processing POST: {e}")
            return Message(payload=f"Error: {str(e)}".encode())


class ClientManagerResource(resource.Resource):
    """Resource that provides information about connected clients (anonymized)"""
    def __init__(self, message_resource):
        super().__init__()
        self.message_resource = message_resource
        self.obfuscator = message_resource.obfuscator

    async def render_get(self, request):
        try:
            # Apply random delay for timing obfuscation
            await self.obfuscator.apply_random_delay()
            
            client_count = len(self.message_resource.clients)
            
            # Generate anonymized client identifiers
            anonymized_clients = [
                f"User-{hash(str(client)) % 1000}" 
                for client in self.message_resource.clients
            ]
            
            response = f"Connected clients ({client_count}):\n" + "\n".join(anonymized_clients)
            
            # Pad response to normalize size
            payload = response.encode()
            payload = self.obfuscator.add_padding(payload)
            payload = self.obfuscator.normalize_message_size(payload)
            
            return Message(payload=payload)
        except Exception as e:
            logger.error(f"Error in clients handler: {e}")
            return Message(payload=f"Error: {str(e)}".encode())


def get_local_ip():
    """Get the primary local IP address"""
    try:
        # Create a socket connection to an external server
        # This is a trick to determine the local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback to localhost if we can't determine IP
        logger.warning("Could not determine local IP address, falling back to localhost")
        return "127.0.0.1"


async def main():
    try:
        logger.info("Initializing metadata-resistant CoAP server...")
        
        # Initialize privacy-enhancing components
        obfuscator = TrafficObfuscator(
            min_delay=settings.MIN_DELAY,
            max_delay=settings.MAX_DELAY,
            padding_probability=settings.PADDING_PROBABILITY,
            padding_size_range=(settings.MIN_PADDING, settings.MAX_PADDING),
            frequency_hop_interval=(settings.MIN_HOP_INTERVAL, settings.MAX_HOP_INTERVAL)
        )
        
        timing_obfuscator = TimingObfuscator(
            fixed_interval=settings.FIXED_INTERVAL,
            jitter_range=(settings.MIN_JITTER, settings.MAX_JITTER),
            dummy_msg_probability=settings.DUMMY_MSG_PROBABILITY
        )
        
        metadata_protection = MetadataProtection()
        
        # Initialize Tor proxy if enabled
        if settings.USE_TOR:
            logger.info("Setting up Tor proxy integration...")
            tor_proxy = TorProxy(
                socks_port=settings.TOR_SOCKS_PORT,
                control_port=settings.TOR_CONTROL_PORT,
                control_password=settings.TOR_CONTROL_PASSWORD,
                use_new_circuit=settings.USE_NEW_TOR_CIRCUIT,
                circuit_change_interval=settings.TOR_CIRCUIT_INTERVAL
            )
            
            if not await tor_proxy.start():
                logger.warning("Failed to initialize Tor proxy, continuing without anonymization")
        
        # Create resource tree
        root = resource.Site()
        message_resource = PrivacyEnhancedResource(obfuscator, timing_obfuscator, metadata_protection)

        # Add resources to the tree
        root.add_resource(['messages'], message_resource)
        root.add_resource(['clients'], ClientManagerResource(message_resource))

        # DTLS credentials using CredentialsMap
        credentials = DTLSEncryption.create_server_credentials(
            settings.PSK_IDENTITY, 
            settings.PSK_KEY
        )
        
        # Get local IP address instead of using any-address
        local_ip = get_local_ip()
        
        # Apply any current frequency hop offset to the port
        port_offset = obfuscator.get_current_port_offset()
        bind_port = settings.SERVER_PORT + port_offset
        
        bind_addr = (local_ip, bind_port)
        
        logger.info(f"🚀 Starting metadata-resistant CoAP server on {local_ip}:{bind_port}...")
        logger.info(f"🔐 DTLS security enabled")
        if settings.USE_TOR:
            logger.info(f"🧅 Tor anonymization enabled")

        # Create server context with explicit bind address and using CredentialsMap
        server_context = await Context.create_server_context(
            root,
            bind=bind_addr,
            server_credentials=credentials  # CredentialsMap
        )
        
        # Create a task to handle frequency hopping port changes
        if settings.ENABLE_FREQUENCY_HOPPING:
            asyncio.create_task(frequency_hopping_task(server_context, obfuscator, local_ip))
        
        logger.info(f"Server running at coap://{local_ip}:{bind_port}/")
        logger.info(f"To connect, use: python client.py --host {local_ip} --port {bind_port}")
        print(f"Server IP address: {local_ip}")
        print(f"Server Port: {bind_port}")
        
        # Keep the server running indefinitely
        await asyncio.get_running_loop().create_future()

    except Exception as e:
        logger.error(f"Error starting server: {e}")

async def frequency_hopping_task(server_context, obfuscator, local_ip):
    """Background task to periodically change server port (frequency hopping)"""
    while True:
        # Wait for a random interval
        hop_interval = random.uniform(
            settings.MIN_HOP_INTERVAL, 
            settings.MAX_HOP_INTERVAL
        )
        await asyncio.sleep(hop_interval)
        
        # Get new port offset
        port_offset = obfuscator.get_next_frequency_hop()
        if port_offset is not None:
            try:
                # Close current server
                await server_context.shutdown()
                
                # Create new server on new port
                new_port = settings.SERVER_PORT + port_offset
                bind_addr = (local_ip, new_port)

                # Create new resource tree
                root = resource.Site()
                message_resource = PrivacyEnhancedResource(
                    obfuscator, 
                    TimingObfuscator(
                        fixed_interval=settings.FIXED_INTERVAL,
                        jitter_range=(settings.MIN_JITTER, settings.MAX_JITTER),
                        dummy_msg_probability=settings.DUMMY_MSG_PROBABILITY
                    ),
                    MetadataProtection()
                )
                root.add_resource(['messages'], message_resource)
                root.add_resource(['clients'], ClientManagerResource(message_resource))
                
                # Get new DTLS credentials using CredentialsMap
                credentials = DTLSEncryption.create_server_credentials(
                    settings.PSK_IDENTITY, 
                    settings.PSK_KEY
                )
                
                # Create server on new port with CredentialsMap
                server_context = await Context.create_server_context(
                    root, 
                    bind=bind_addr, 
                    server_credentials=credentials
                )
                
                logger.info(f"🔀 Frequency hop: Server moved to port {new_port}")
                
            except Exception as e:
                logger.error(f"Error during frequency hop: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutdown by user")
        logger.info("Server shutdown by user")