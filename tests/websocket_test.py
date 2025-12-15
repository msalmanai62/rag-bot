"""
WebSocket endpoint test script for RAG Chat application.
Tests the WebSocket connection, message sending, and response streaming.
"""

import asyncio
import websockets
import json
from datetime import datetime


class WebSocketTester:
    def __init__(self, base_url: str = "ws://localhost:8000"):
        self.base_url = base_url
        self.user_id = "string123"
        self.chat_id = "3993810e-b455-4f1d-81fe-45b89a869dc9"

    # async def create_chat_via_http(self):
    #     """Create a test chat using HTTP before testing WebSocket."""
    #     import aiohttp
        
    #     async with aiohttp.ClientSession() as session:
    #         url = "http://localhost:8000/api/chats"
    #         payload = {
    #             "user_id": self.user_id,
    #             "name": "WebSocket Test Chat",
    #             "default_url": None
    #         }
            
    #         try:
    #             async with session.post(url, json=payload) as resp:
    #                 if resp.status == 200:
    #                     data = await resp.json()
    #                     self.chat_id = data.get("chat_id")
    #                     print(f"✓ Chat created successfully: {self.chat_id}")
    #                     return True
    #                 else:
    #                     print(f"✗ Failed to create chat: {resp.status}")
    #                     return False
    #         except Exception as e:
    #             print(f"✗ Error creating chat: {e}")
    #             return False

    async def test_websocket_connection(self):
        """Test basic WebSocket connection."""
        if not self.chat_id:
            print("✗ Cannot test WebSocket - no chat ID available")
            return False

        ws_url = f"{self.base_url}/api/ws/{self.user_id}/{self.chat_id}"
        print(f"\nConnecting to: {ws_url}")
        
        try:
            async with websockets.connect(ws_url) as websocket:
                print("✓ WebSocket connection established")
                print("Enter messages (Ctrl+C to exit):\n")
                
                message_count = 0
                while True:
                    try:
                        # Get user input (non-blocking in async context)
                        test_message = await asyncio.get_event_loop().run_in_executor(None, input, "You: ")
                        
                        if not test_message.strip():
                            continue
                        
                        message_count += 1
                        print(f"[Msg {message_count}] Sending: {test_message}")
                        await websocket.send(test_message)
                        
                        # Receive streaming response
                        print("Bot: ", end="", flush=True)
                        full_response = ""
                        chunk_count = 0
                        response_complete = False
                        
                        # Keep receiving until we get the completion signal
                        while not response_complete:
                            try:
                                chunk = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                                
                                if chunk == "__END__":
                                    # Response complete
                                    response_complete = True
                                    break
                                
                                if chunk.startswith("__error__:"):
                                    error_msg = chunk[10:]
                                    print(f"\n✗ Error: {error_msg}")
                                    response_complete = True
                                    break
                                
                                # Regular response chunk
                                print(chunk, end="", flush=True)
                                full_response += chunk
                                chunk_count += 1
                                
                            except asyncio.TimeoutError:
                                # Timeout - stream ended
                                print(f"\n[Stream timeout after {chunk_count} chunks]")
                                response_complete = True
                                break
                        
                        print(f"\n✓ Response complete ({chunk_count} chunks, {len(full_response)} chars)\n")
                        
                    except KeyboardInterrupt:
                        print("\n\n✓ Gracefully shutting down...")
                        return True
                    except websockets.exceptions.ConnectionClosed as e:
                        print(f"\n✗ WebSocket disconnected: {e}")
                        return False
            
        except Exception as e:
            print(f"✗ WebSocket error: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_multiple_messages(self):
        """Test sending multiple messages in sequence."""
        if not self.chat_id:
            print("✗ Cannot test WebSocket - no chat ID available")
            return False

        ws_url = f"{self.base_url}/api/ws/{self.user_id}/{self.chat_id}"
        test_messages = [
            "Hello, what is AI?",
            "Tell me about neural networks",
            "What is a transformer?"
        ]
        
        try:
            async with websockets.connect(ws_url) as websocket:
                print("✓ WebSocket connection established for multi-message test")
                
                for i, message in enumerate(test_messages, 1):
                    print(f"\n[Message {i}] Sending: {message}")
                    await websocket.send(message)
                    
                    print("Response: ", end="", flush=True)
                    response = ""
                    chunk_count = 0
                    
                    try:
                        while True:
                            chunk = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                            
                            if chunk.startswith("__error__:"):
                                error_msg = chunk[10:]
                                print(f"\n✗ Error: {error_msg}")
                                break
                            
                            print(chunk[:50] + "..." if len(chunk) > 50 else chunk, end=" ", flush=True)
                            response += chunk
                            chunk_count += 1
                            
                    except asyncio.TimeoutError:
                        print("\n✗ Timeout")
                        break
                    except websockets.exceptions.ConnectionClosed:
                        print("[Connection closed]")
                        break
                    
                    print(f"\n✓ Message {i} complete ({chunk_count} chunks, {len(response)} chars)")
                
                return True
                
        except Exception as e:
            print(f"✗ Error in multi-message test: {e}")
            return False

async def run_all_tests():
    """Run all WebSocket tests."""
    print("=" * 60)
    print("RAG Chat WebSocket Test Suite")
    print("=" * 60)

    tester = WebSocketTester()
    
    # Step 2: Test basic connection
    print("\n[Step 2] Testing basic WebSocket connection and streaming...")
    await tester.test_websocket_connection()
   




if __name__ == "__main__":
    print("Starting WebSocket tests...\n")
    print("Make sure:")
    print("1. FastAPI server is running on http://localhost:8000")
    print("2. RAG service is initialized")
    print("3. GOOGLE_API_KEY is set in environment\n")
    
    asyncio.run(run_all_tests())
