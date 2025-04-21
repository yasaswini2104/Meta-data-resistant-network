#test_server.py
import asyncio
import logging
import sys
from pathlib import Path
import time
import random

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from aiocoap import resource, Context, Message
import aiocoap

from core.encryption import DTLSEncryption
from core.obfuscation import TrafficObfuscator
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-server")

class TestResource(resource.Resource):
    """Test resource for server performance testing"""
    
    def __init__(self):
        super().__init__()
        self.received_messages = 0
        self.obfuscator = TrafficObfuscator()
        self.start_time = time.time()
    
    async def render_get(self, request):
        """Handle GET requests for status information"""
        try:
            # Apply random delay to simulate obfuscation
            await self.obfuscator.apply_random_delay()
            
            # Calculate uptime and message rate
            uptime = time.time() - self.start_time
            rate = self.received_messages / uptime if uptime > 0 else 0
            
            status = (
                f"Test Server Status\n"
                f"Uptime: {uptime:.1f} seconds\n"
                f"Received Messages: {self.received_messages}\n"
                f"Message Rate: {rate:.2f} msgs/sec\n"
            )
            
            return Message(payload=status.encode())
            
        except Exception as e:
            logger.error(f"Error in GET handler: {e}")
            return Message(payload=f"Error: {str(e)}".encode())
    
    async def render_post(self, request):
        """Handle POST requests for test messages"""
        try:
            # Apply random delay to simulate obfuscation
            await self.obfuscator.apply_random_delay()
            
            # Process the message
            self.received_messages += 1
            
            # Log the message receipt (but don't decode for privacy)
            logger.debug(f"Received message #{self.received_messages} of size {len(request.payload)} bytes")
            
            # Create and send response
            response = f"Acknowledged: Message #{self.received_messages}"
            
            # Apply padding to response
            payload = self.obfuscator.add_padding(response.encode())
            
            return Message(payload=payload)
            
        except Exception as e:
            logger.error(f"Error in POST handler: {e}")
            return Message(payload=f"Error: {str(e)}".encode())

class PerformanceTestResource(resource.Resource):
    """Resource for server performance testing"""
    
    def __init__(self):
        super().__init__()
        self.test_running = False
        self.test_start_time = 0
        self.test_messages = 0
        self.test_latencies = []
    
    async def render_post(self, request):
        """Start or stop a performance test"""
        try:
            command = request.payload.decode().strip()
            
            if command == "start":
                # Start a new test
                self.test_running = True
                self.test_start_time = time.time()
                self.test_messages = 0
                self.test_latencies = []
                logger.info("Performance test started")
                return Message(payload=b"Test started")
                
            elif command == "stop":
                # Stop current test and return results
                self.test_running = False
                duration = time.time() - self.test_start_time
                
                if not self.test_messages:
                    return Message(payload=b"No messages received in test")
                
                avg_latency = sum(self.test_latencies) / len(self.test_latencies) if self.test_latencies else 0
                throughput = self.test_messages / duration if duration > 0 else 0
                
                results = (
                    f"Performance Test Results:\n"
                    f"Duration: {duration:.2f} seconds\n"
                    f"Messages: {self.test_messages}\n"
                    f"Throughput: {throughput:.2f} msgs/sec\n"
                    f"Avg Latency: {avg_latency*1000:.2f} ms\n"
                )
                
                if self.test_latencies:
                    results += f"Min Latency: {min(self.test_latencies)*1000:.2f} ms\n"
                    results += f"Max Latency: {max(self.test_latencies)*1000:.2f} ms\n"
                
                logger.info("Performance test completed")
                return Message(payload=results.encode())
                
            else:
                return Message(payload=b"Unknown command. Use 'start' or 'stop'")
                
        except Exception as e:
            logger.error(f"Error in performance test handler: {e}")
            return Message(payload=f"Error: {str(e)}".encode())
    
    def record_message(self, latency):
        """Record a message for the performance test"""
        if self.test_running:
            self.test_messages += 1
            self.test_latencies.append(latency)

async def main():
    try:
        # Create resource tree
        root = resource.Site()
        test_resource = TestResource()
        perf_resource = PerformanceTestResource()
        
        # Add resources to tree
        root.add_resource(['test'], test_resource)
        root.add_resource(['performance'], perf_resource)
        
        # Create DTLS server credentials
        credentials = DTLSEncryption.create_server_credentials(
            settings.PSK_IDENTITY, 
            settings.PSK_KEY
        )
        
        # Choose a random port for the test server
        test_port = random.randint(5700, 5799)
        
        # Start server
        logger.info(f"Starting test server on port {test_port}")
        server_context = await Context.create_server_context(
            root, 
            bind=('0.0.0.0', test_port), 
            server_credentials=credentials
        )
        
        print(f"Test server running at coap://localhost:{test_port}/")
        print(f"For performance testing: coap://localhost:{test_port}/performance")
        print("Press Ctrl+C to stop the server")
        
        # Keep the server running
        await asyncio.get_running_loop().create_future()
        
    except Exception as e:
        logger.error(f"Error starting test server: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Test server shutdown by user")