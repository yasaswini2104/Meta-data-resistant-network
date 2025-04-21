import asyncio
import logging
import sys
import time
import random
import argparse
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from aiocoap import Message, Context
import aiocoap

from core.encryption import DTLSEncryption
from core.obfuscation import TrafficObfuscator
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("traffic-simulation")

class SimulatedClient:
    """
    Simulates a client for traffic pattern testing
    """
    def __init__(self, server_host, server_port, client_id, message_pattern='random'):
        """
        Initialize a simulated client
        
        Args:
            server_host: Host address of the server
            server_port: Port of the server
            client_id: Unique client identifier
            message_pattern: Pattern for message timing ('random', 'burst', 'periodic')
        """
        self.server_host = server_host
        self.server_port = server_port
        self.client_id = client_id
        self.message_pattern = message_pattern
        self.context = None
        self.obfuscator = TrafficObfuscator()
        self.sent_messages = 0
        self.received_responses = 0
        self.active = True
    
    async def setup(self):
        """Set up the client"""
        try:
            credentials = DTLSEncryption.create_client_credentials(
                settings.PSK_IDENTITY, 
                settings.PSK_KEY
            )
            self.context = await Context.create_client_context(client_credentials=credentials)
            logger.info(f"Client {self.client_id} initialized with {self.message_pattern} message pattern")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize client {self.client_id}: {e}")
            return False
    
    async def send_message(self):
        """Send a single message to the server"""
        try:
            self.sent_messages += 1
            message_id = self.sent_messages
            
            # Create message with some content
            content = f"Message {message_id} from {self.client_id}"
            payload = content.encode()
            
            # Apply obfuscation if enabled
            payload = self.obfuscator.add_padding(payload)
            payload = self.obfuscator.normalize_message_size(payload)
            
            # Prepare request
            request = Message(
                code=aiocoap.POST,
                uri=f'coap://{self.server_host}:{self.server_port}/messages',
                payload=payload
            )
            
            # Send request with appropriate delay pattern
            await self.obfuscator.apply_random_delay()
            
            # Send and get response
            response = await self.context.request(request).response
            
            # Process response
            if response.code.is_successful():
                self.received_responses += 1
                logger.debug(f"Client {self.client_id}: Message {message_id} sent successfully")
                return True
            else:
                logger.warning(f"Client {self.client_id}: Message {message_id} failed: {response.code}")
                return False
                
        except asyncio.TimeoutError:
            logger.error(f"Client {self.client_id}: Request timed out")
            return False
        except Exception as e:
            logger.error(f"Client {self.client_id}: Error sending message: {e}")
            return False
    
    async def run_pattern(self):
        """Run the selected message pattern"""
        if self.message_pattern == 'random':
            await self.run_random_pattern()
        elif self.message_pattern == 'burst':
            await self.run_burst_pattern()
        elif self.message_pattern == 'periodic':
            await self.run_periodic_pattern()
        else:
            logger.error(f"Unknown message pattern: {self.message_pattern}")
    
    async def run_random_pattern(self):
        """Send messages with random intervals"""
        while self.active:
            # Random delay between 1-10 seconds
            delay = random.uniform(1, 10)
            await asyncio.sleep(delay)
            
            if self.active:
                await self.send_message()
    
    async def run_burst_pattern(self):
        """Send messages in bursts with pauses between"""
        while self.active:
            # Send a burst of 3-8 messages
            burst_size = random.randint(3, 8)
            logger.info(f"Client {self.client_id}: Sending burst of {burst_size} messages")
            
            for _ in range(burst_size):
                if not self.active:
                    break
                    
                await self.send_message()
                # Small delay between messages in burst
                await asyncio.sleep(random.uniform(0.1, 0.5))
            
            # Longer pause between bursts (10-30 seconds)
            if self.active:
                pause = random.uniform(10, 30)
                logger.info(f"Client {self.client_id}: Pausing for {pause:.1f} seconds")
                await asyncio.sleep(pause)
    
    async def run_periodic_pattern(self):
        """Send messages at regular intervals"""
        # Choose a random period between 3-7 seconds
        period = random.uniform(3, 7)
        logger.info(f"Client {self.client_id}: Using period of {period:.1f} seconds")
        
        while self.active:
            await self.send_message()
            await asyncio.sleep(period)
    
    async def stop(self):
        """Stop the client"""
        self.active = False
        if self.context:
            await self.context.shutdown()
        logger.info(f"Client {self.client_id}: Stopped after sending {self.sent_messages} messages")

class TrafficSimulation:
    """
    Simulates multiple clients with different traffic patterns
    """
    def __init__(self, server_host, server_port, num_clients=5, duration=60):
        """
        Initialize traffic simulation
        
        Args:
            server_host: Host address of the server
            server_port: Port of the server
            num_clients: Number of clients to simulate
            duration: Duration of simulation in seconds
        """
        self.server_host = server_host
        self.server_port = server_port
        self.num_clients = num_clients
        self.duration = duration
        self.clients = []
        self.patterns = ['random', 'burst', 'periodic']
    
    async def setup_clients(self):
        """Set up all simulated clients"""
        for i in range(self.num_clients):
            # Choose a random pattern
            pattern = random.choice(self.patterns)
            
            # Create client
            client = SimulatedClient(
                self.server_host,
                self.server_port,
                f"SimClient-{i+1}",
                pattern
            )
            
            # Set up client
            if await client.setup():
                self.clients.append(client)
        
        logger.info(f"Set up {len(self.clients)} simulated clients")
        return len(self.clients) > 0
    
    async def run(self):
        """Run the traffic simulation"""
        if not self.clients:
            logger.error("No clients set up. Cannot run simulation.")
            return
        
        # Start all clients
        client_tasks = [asyncio.create_task(client.run_pattern()) for client in self.clients]
        
        # Run for specified duration
        logger.info(f"Running traffic simulation for {self.duration} seconds")
        await asyncio.sleep(self.duration)
        
        # Stop all clients
        for client in self.clients:
            await client.stop()
        
        # Wait for all clients to complete
        for task in client_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Log results
        total_messages = sum(client.sent_messages for client in self.clients)
        total_responses = sum(client.received_responses for client in self.clients)
        success_rate = (total_responses / total_messages * 100) if total_messages > 0 else 0
        
        print("\n=== Traffic Simulation Results ===")
        print(f"Duration: {self.duration} seconds")
        print(f"Clients: {len(self.clients)}")
        print(f"Total Messages: {total_messages}")
        print(f"Successful Responses: {total_responses}")
        print(f"Success Rate: {success_rate:.1f}%")
        print("Pattern distribution:")
        for pattern in self.patterns:
            count = sum(1 for client in self.clients if client.message_pattern == pattern)
            print(f"  - {pattern}: {count} clients")
        print("================================")

async def main():
    parser = argparse.ArgumentParser(description='Traffic simulation for metadata-resistant network')
    parser.add_argument('--host', default='localhost', help='Server hostname')
    parser.add_argument('--port', type=int, default=5684, help='Server port')
    parser.add_argument('--clients', type=int, default=5, help='Number of clients to simulate')
    parser.add_argument('--duration', type=int, default=60, help='Duration of simulation in seconds')
    args = parser.parse_args()
    
    simulation = TrafficSimulation(
        args.host,
        args.port,
        args.clients,
        args.duration
    )
    
    if await simulation.setup_clients():
        await simulation.run()
    else:
        logger.error("Failed to set up clients. Aborting simulation.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")