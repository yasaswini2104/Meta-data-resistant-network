# core/obfuscation.py
import random
import asyncio
import logging
import time
import math
from collections import deque

logger = logging.getLogger('obfuscation')

class TrafficObfuscator:
    """
    Implements various traffic obfuscation techniques to prevent
    metadata analysis based on traffic patterns
    """
    def __init__(self, 
                min_delay=0.05, 
                max_delay=0.5, 
                padding_probability=0.3,
                padding_size_range=(50, 200),
                frequency_hop_interval=(5, 15)):
        """
        Initialize obfuscator with configuration parameters
        
        Args:
            min_delay: Minimum random delay in seconds
            max_delay: Maximum random delay in seconds
            padding_probability: Probability of adding padding (0-1)
            padding_size_range: Range of padding bytes to add (min, max)
            frequency_hop_interval: Range of seconds between frequency hops
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.padding_probability = padding_probability
        self.padding_min, self.padding_max = padding_size_range
        self.hop_min, self.hop_max = frequency_hop_interval
        self.message_history = deque(maxlen=100)  # Store recent message sizes
        self.last_hop_time = time.time()
        self.current_port_offset = 0
    
    async def apply_random_delay(self):
        """Apply a random delay before message transmission"""
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"Applying random delay: {delay:.3f}s")
        await asyncio.sleep(delay)
    
    def add_padding(self, message):
        """
        Potentially add random padding to a message
        Returns the padded message or original if no padding applied
        """
        if random.random() < self.padding_probability:
            # Determine padding size
            padding_size = random.randint(self.padding_min, self.padding_max)
            
            # Create padding bytes
            padding = os.urandom(padding_size)
            
            # Add padding with a marker so it can be removed
            padded_message = message + b"||PADDING||" + padding
            
            logger.debug(f"Added {padding_size} bytes of padding")
            return padded_message
        
        return message
    
    def remove_padding(self, message):
        """Remove padding if present in the message"""
        if b"||PADDING||" in message:
            message, _ = message.split(b"||PADDING||", 1)
            logger.debug("Padding removed from message")
        return message
    
    def normalize_message_size(self, message):
        """
        Normalize message size to prevent traffic analysis
        based on message length patterns
        """
        # Calculate average message size from history
        if not self.message_history:
            self.message_history.append(len(message))
            return message
            
        avg_size = sum(self.message_history) / len(self.message_history)
        self.message_history.append(len(message))
        
        # Round up to next power of 2 to normalize size
        target_size = 2 ** math.ceil(math.log2(avg_size))
        
        # If message is smaller than target, pad it
        if len(message) < target_size:
            padding_needed = target_size - len(message)
            padding = b"X" * padding_needed
            normalized = message + b"||SIZE||" + padding
            logger.debug(f"Normalized message size from {len(message)} to {len(normalized)}")
            return normalized
            
        return message
    
    def denormalize_message_size(self, message):
        """Remove size normalization padding"""
        if b"||SIZE||" in message:
            message, _ = message.split(b"||SIZE||", 1)
            logger.debug("Size normalization removed")
        return message
        
    def get_next_frequency_hop(self):
        """
        Check if it's time for a frequency hop and return new port offset
        Returns None if no hop is needed
        """
        current_time = time.time()
        
        # Check if enough time has passed since last hop
        if current_time - self.last_hop_time > random.uniform(self.hop_min, self.hop_max):
            self.last_hop_time = current_time
            # Generate a new port offset (1-10)
            self.current_port_offset = random.randint(1, 10)
            logger.info(f"Frequency hop: port offset {self.current_port_offset}")
            return self.current_port_offset
            
        return None
    
    def get_current_port_offset(self):
        """Get the current port offset for frequency hopping"""
        return self.current_port_offset

import os  # For os.urandom

class TimingObfuscator:
    """
    Handles communication timing obfuscation to make traffic
    analysis more difficult
    """
    def __init__(self, 
                 fixed_interval=None,
                 jitter_range=(0.1, 0.5),
                 dummy_msg_probability=0.2):
        """
        Args:
            fixed_interval: If set, sends messages at fixed intervals (seconds)
            jitter_range: Random jitter to add to interval (min, max seconds)
            dummy_msg_probability: Probability of sending dummy messages
        """
        self.fixed_interval = fixed_interval
        self.min_jitter, self.max_jitter = jitter_range
        self.dummy_msg_probability = dummy_msg_probability
        self.last_send_time = 0
        
    def should_send_dummy(self):
        """Check if a dummy message should be sent"""
        return random.random() < self.dummy_msg_probability
        
    def create_dummy_message(self, avg_size=100):
        """Create a dummy message marked for removal at receiver"""
        # Create a random-sized dummy payload
        size = int(random.gauss(avg_size, avg_size/3))
        size = max(20, min(size, avg_size*2))  # Bound the size
        
        payload = os.urandom(size)
        return b"||DUMMY||" + payload
        
    def is_dummy_message(self, message):
        """Check if a message is a dummy message"""
        return message.startswith(b"||DUMMY||")
        
    def remove_dummy_marker(self, message):
        """Remove dummy marker if present, or return None if it's a dummy"""
        if self.is_dummy_message(message):
            return None  # It's a dummy, discard it
        return message
        
    async def wait_for_next_interval(self):
        """
        Wait until next sending interval if using fixed intervals
        with jitter
        """
        if not self.fixed_interval:
            return
            
        now = time.time()
        jitter = random.uniform(self.min_jitter, self.max_jitter)
        
        # Calculate time since last send
        time_since_last = now - self.last_send_time
        
        # If first message or we've already waited longer than interval
        if self.last_send_time == 0 or time_since_last >= self.fixed_interval:
            self.last_send_time = now
            return
            
        # Calculate remaining wait time
        wait_time = max(0, self.fixed_interval - time_since_last + jitter)
        
        if wait_time > 0:
            logger.debug(f"Waiting {wait_time:.2f}s for next interval")
            await asyncio.sleep(wait_time)
            
        self.last_send_time = time.time()