import asyncio
import logging
import sys
import time
import argparse
import random
import socket
from pathlib import Path

# Add project root to path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

from aiocoap import Context, Message
import aiocoap

from core.encryption import DTLSEncryption, MetadataProtection
from core.obfuscation import TrafficObfuscator, TimingObfuscator
from core.tor_proxy import TorProxy, I2PProxy
from config.settings import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("metadata-resistant-client")

class PrivacyEnhancedClient:
    def __init__(self, 
                 server_host='localhost', 
                 server_port=5684, 
                 client_id=None,
                 obfuscator=None,
                 timing_obfuscator=None,
                 metadata_protection=None,
                 anonymizer=None):
        """
        Initialize the privacy-enhanced CoAP client
        
        Args:
            server_host: CoAP server hostname
            server_port: CoAP server port
            client_id: Client identifier 
            obfuscator: TrafficObfuscator instance
            timing_obfuscator: TimingObfuscator instance
            metadata_protection: MetadataProtection instance
            anonymizer: TorProxy or I2PProxy instance
        """
        self.server_host = server_host
        self.server_port = server_port
        self.client_id = client_id or f"Client-{time.strftime('%H%M%S')}"
        self.running = True
        self.context = None
        
        # Privacy components
        self.obfuscator = obfuscator or TrafficObfuscator()
        self.timing_obfuscator = timing_obfuscator or TimingObfuscator()
        self.metadata_protection = metadata_protection or MetadataProtection()
        self.anonymizer = anonymizer
        
        # Keep track of frequency hops
        self.current_port_offset = 0
        self.last_port_check = 0
        
        # Make client ID more anonymous if not specified
        if client_id is None:
            # Use hash of hostname + random value to avoid tracking
            random_base = f"{socket.gethostname()}-{random.randint(10000, 99999)}"
            self.client_id = f"User-{hash(random_base) % 10000}"

    async def setup(self):
        """Initialize the client with privacy-enhancing features"""
        try:
            # First set up anonymizer if configured
            if self.anonymizer:
                if not await self.anonymizer.start():
                    logger.warning("Failed to start anonymization service, continuing without it")
            
            # Load the client credentials using PSK with CredentialsMap
            credentials = DTLSEncryption.create_client_credentials(
                settings.PSK_IDENTITY, 
                settings.PSK_KEY
            )
            
            # Create client context with credentials
            self.context = await Context.create_client_context(client_credentials=credentials)
            
            logger.info(f"Client {self.client_id} initialized with privacy enhancements")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
            return False

    async def send_request(self, method, path, payload=None):
        """Send a request with privacy-enhancing features applied"""
        try:
            # Check if we need to update server port for frequency hopping
            current_time = time.time()
            if settings.ENABLE_FREQUENCY_HOPPING and current_time - self.last_port_check >= 5:
                self.last_port_check = current_time
                new_offset = self.obfuscator.get_next_frequency_hop()
                if new_offset is not None and new_offset != self.current_port_offset:
                    self.current_port_offset = new_offset
                    self.server_port = settings.SERVER_PORT + new_offset
                    logger.info(f"Updated server port to {self.server_port} (offset +{new_offset})")
            
            # Apply random delay for timing obfuscation
            await self.obfuscator.apply_random_delay()
            
            # Wait for next interval if using fixed interval timing
            await self.timing_obfuscator.wait_for_next_interval()
            
            # Prepare payload with obfuscation if provided
            if payload:
                if isinstance(payload, str):
                    payload = payload.encode()
                    
                # Add padding and normalize size
                payload = self.obfuscator.add_padding(payload)
                payload = self.obfuscator.normalize_message_size(payload)
            
            # Check if we should send a dummy message instead
            if self.timing_obfuscator.should_send_dummy() and method == aiocoap.POST:
                logger.debug("Sending dummy message for traffic obfuscation")
                payload = self.timing_obfuscator.create_dummy_message()
            
            # Create the request
            request = Message(
                code=method,
                uri=f'coap://{self.server_host}:{self.server_port}/{path}',
                payload=payload
            )
            
            # Send the request
            response = await self.context.request(request).response
            
            # Process the response
            if response.payload:
                # Remove any obfuscation
                payload = self.obfuscator.remove_padding(response.payload)
                payload = self.obfuscator.denormalize_message_size(payload)
                
                # Check if it's a dummy response
                if self.timing_obfuscator.is_dummy_message(payload):
                    logger.debug("Received dummy response, discarding")
                    return None
                    
                return payload
            return None
            
        except asyncio.TimeoutError:
            logger.error(f"Request timed out. Server at {self.server_host}:{self.server_port} not responding.")
            return None
        except Exception as e:
            logger.error(f"Error in request: {e}")
            return None

    async def get_messages(self):
        """Retrieve all messages from the server"""
        try:
            response_payload = await self.send_request(aiocoap.GET, "messages")
            
            if response_payload:
                print(f"\n=== Server Response ===\n{response_payload.decode()}\n======================")
                return True
            else:
                print(f"\nUnable to connect to server at {self.server_host}:{self.server_port}.")
                print("Please check if the server is running and the address is correct.")
                return False
                
        except Exception as e:
            logger.error(f"Error in GET request: {e}")
            print(f"\nError connecting to server: {str(e)}")
            return False

    async def get_clients(self):
        """Get information about connected clients"""
        try:
            response_payload = await self.send_request(aiocoap.GET, "clients")
            
            if response_payload:
                print(f"\n=== Connected Clients ===\n{response_payload.decode()}\n========================")
                return True
            else:
                print("\nUnable to retrieve client list. Server not responding.")
                return False
                
        except Exception as e:
            logger.error(f"Error getting client list: {e}")
            print(f"\nError retrieving client list: {str(e)}")
            return False

    async def send_message(self, message):
        """Send a message to the server"""
        try:
            payload = f"{self.client_id}: {message}"
            response_payload = await self.send_request(aiocoap.POST, "messages", payload)
            
            if response_payload:
                logger.info(f"Message sent successfully")
                return True
            else:
                print("\nMessage could not be sent. Server not responding.")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            print(f"\nError sending message: {str(e)}")
            return False

    async def interactive_loop(self):
        """Run an interactive command loop with enhanced privacy"""
        # Initial message retrieval
        connected = await self.get_messages()
        if not connected:
            print(f"\nCould not establish initial connection to {self.server_host}:{self.server_port}")
            print("Make sure the server is running and the address is correct.")
            print(f"Try: python client.py --host <server_ip> --port <server_port>")
            self.running = False
            return

        print(f"\nWelcome to the Metadata-Resistant CoAP Network!")
        print(f"You are connected as: {self.client_id}")
        print("Your connection is protected by:")
        print("  • DTLS encryption for message security")
        print("  • Traffic padding to prevent size analysis")
        print("  • Timing obfuscation to prevent timing analysis")
        if self.anonymizer and getattr(self.anonymizer, 'active', False):
            if isinstance(self.anonymizer, TorProxy):
                print("  • Tor network anonymization")
            elif isinstance(self.anonymizer, I2PProxy):
                print("  • I2P network anonymization")
        
        print("\nAvailable commands:")
        print("  /help - Show this help")
        print("  /exit - Exit the client")
        print("  /list - List connected clients")
        print("  /refresh - Get latest messages")
        print("  /status - Show privacy protection status")
        if isinstance(self.anonymizer, TorProxy) and getattr(self.anonymizer, 'active', False):
            print("  /newcircuit - Request a new Tor circuit")
        print("  Any other text will be sent as a message")

        while self.running:
            try:
                message = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\nEnter message (or /command): ")
                )

                if not message:
                    continue

                if message.lower() == "/exit":
                    self.running = False
                    print("Exiting...")
                    continue

                if message.lower() == "/help":
                    print("Available commands:")
                    print("  /help - Show this help")
                    print("  /exit - Exit the client")
                    print("  /list - List connected clients")
                    print("  /refresh - Get latest messages")
                    print("  /status - Show privacy protection status")
                    if isinstance(self.anonymizer, TorProxy) and getattr(self.anonymizer, 'active', False):
                        print("  /newcircuit - Request a new Tor circuit")
                    print("  Any other text will be sent as a message")
                    continue

                if message.lower() == "/list":
                    await self.get_clients()
                    continue

                if message.lower() == "/refresh":
                    await self.get_messages()
                    continue
                    
                if message.lower() == "/status":
                    print("\n=== Privacy Protection Status ===")
                    print(f"Connection Type: CoAP over DTLS")
                    print(f"Traffic Obfuscation: Active")
                    print(f"  - Padding Probability: {self.obfuscator.padding_probability}")
                    print(f"  - Random Delay Range: {self.obfuscator.min_delay}-{self.obfuscator.max_delay}s")
                    if settings.ENABLE_FREQUENCY_HOPPING:
                        print(f"Frequency Hopping: Active (current port: {self.server_port})")
                    else:
                        print(f"Frequency Hopping: Disabled")
                    if self.anonymizer and getattr(self.anonymizer, 'active', False):
                        if isinstance(self.anonymizer, TorProxy):
                            print(f"Anonymization: Tor network (SOCKS port: {self.anonymizer.socks_port})")
                        elif isinstance(self.anonymizer, I2PProxy):
                            print(f"Anonymization: I2P network (SOCKS port: {self.anonymizer.socks_proxy_port})")
                    else:
                        print(f"Anonymization: Disabled")
                    print("================================")
                    continue
                    
                if message.lower() == "/newcircuit" and isinstance(self.anonymizer, TorProxy):
                    if await self.anonymizer.new_circuit():
                        print("Requested new Tor circuit - your connection path has changed")
                    else:
                        print("Failed to request new Tor circuit")
                    continue

                # Regular message
                sent = await self.send_message(message)
                if sent:
                    # Refresh messages after sending successfully
                    await self.get_messages()

            except asyncio.CancelledError:
                self.running = False
            except Exception as e:
                logger.error(f"Error in interactive loop: {e}")

    async def run(self):
        """Main client run method"""
        setup_ok = await self.setup()
        if setup_ok:
            await self.interactive_loop()

        # Cleanup
        if self.context:
            await self.context.shutdown()
            
        # Shutdown anonymizer if active
        if self.anonymizer and getattr(self.anonymizer, 'active', False):
            await self.anonymizer.stop()


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Metadata-Resistant CoAP Client')
    parser.add_argument('--host', default='localhost', help='CoAP server hostname')
    parser.add_argument('--port', type=int, default=5684, help='CoAP server port')
    parser.add_argument('--tor', action='store_true', help='Enable Tor anonymization')
    parser.add_argument('--i2p', action='store_true', help='Enable I2P anonymization')
    args = parser.parse_args()

    # Choose anonymizer
    anonymizer = None
    if args.tor:
        anonymizer = TorProxy(
            socks_port=settings.TOR_SOCKS_PORT,
            control_port=settings.TOR_CONTROL_PORT,
            control_password=settings.TOR_CONTROL_PASSWORD,
            use_new_circuit=settings.USE_NEW_TOR_CIRCUIT,
            circuit_change_interval=settings.TOR_CIRCUIT_INTERVAL
        )
    elif args.i2p:
        anonymizer = I2PProxy(
            socks_proxy_port=settings.I2P_SOCKS_PORT
        )

    client = PrivacyEnhancedClient(
        server_host=args.host,
        server_port=args.port,
        anonymizer=anonymizer
    )

    await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Client shutdown by user.")
        logger.info("Client shutdown by user.")
