# tests/test_client.py
import asyncio
import logging
import sys
import time
import random
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from aiocoap import Message, Context
import aiocoap
from core.encryption import DTLSEncryption
from core.obfuscation import TrafficObfuscator
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-client")

class TestClient:
    """
    Test client for simulating and validating metadata-resistant features
    """
    def __init__(self, server_host='localhost', server_port=5684):
        self.server_host = server_host
        self.server_port = server_port
        self.client_id = f"TestClient-{random.randint(1000, 9999)}"
        self.context = None
        self.obfuscator = TrafficObfuscator()
        self.total_requests = 0
        self.successful_requests = 0
        self.latencies = []
    
    async def setup(self):
        """Set up the test client with DTLS credentials"""
        try:
            credentials = DTLSEncryption.create_client_credentials(
                settings.PSK_IDENTITY, settings.PSK_KEY
            )
            self.context = await Context.create_client_context(client_credentials=credentials)
            logger.info(f"Test client {self.client_id} initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize test client: {e}")
            return False
    
    async def send_test_message(self, message_id):
        """Send a test message and measure latency"""
        try:
            self.total_requests += 1
            
            # Prepare the test message
            payload = f"Test message {message_id} from {self.client_id}"
            
            # Apply obfuscation
            padded_payload = self.obfuscator.add_padding(payload.encode())
            
            # Prepare the request
            request = Message(
                code=aiocoap.POST,
                uri=f'coap://{self.server_host}:{self.server_port}/messages',
                payload=padded_payload
            )
            
            # Measure latency
            start_time = time.time()
            await self.obfuscator.apply_random_delay()  # Apply random delay
            
            # Send the request
            response = await self.context.request(request).response
            
            # Calculate latency (subtract the artificial delay)
            latency = time.time() - start_time
            self.latencies.append(latency)
            
            if response.code.is_successful():
                self.successful_requests += 1
                logger.debug(f"Message {message_id} sent successfully. Latency: {latency:.3f}s")
                return True
            else:
                logger.warning(f"Message {message_id} failed with code: {response.code}")
                return False
                
        except asyncio.TimeoutError:
            logger.error(f"Request {message_id} timed out")
            return False
        except Exception as e:
            logger.error(f"Error sending message {message_id}: {e}")
            return False
    
    def print_stats(self):
        """Print test statistics"""
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        
        print("\n=== Test Results ===")
        print(f"Total Requests: {self.total_requests}")
        print(f"Successful Requests: {self.successful_requests}")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Average Latency: {avg_latency:.3f}s")
        if self.latencies:
            print(f"Min Latency: {min(self.latencies):.3f}s")
            print(f"Max Latency: {max(self.latencies):.3f}s")
        print("===================")

async def run_test(host, port, message_count, interval):
    """Run a automated test with the specified parameters"""
    client = TestClient(host, port)
    
    if not await client.setup():
        logger.error("Failed to set up test client. Aborting test.")
        return
    
    print(f"Starting test: Sending {message_count} messages at {interval:.1f}s intervals")
    
    for i in range(1, message_count + 1):
        await client.send_test_message(i)
        await asyncio.sleep(interval)
    
    client.print_stats()
    
    # Clean up
    await client.context.shutdown()

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Metadata-Resistant Network Test Client')
    parser.add_argument('--host', default='localhost', help='Server hostname')
    parser.add_argument('--port', type=int, default=5684, help='Server port')
    parser.add_argument('--count', type=int, default=20, help='Number of test messages to send')
    parser.add_argument('--interval', type=float, default=0.5, help='Interval between messages (seconds)')
    args = parser.parse_args()
    
    await run_test(args.host, args.port, args.count, args.interval)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")