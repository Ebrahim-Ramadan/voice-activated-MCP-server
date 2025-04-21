import os
import speech_recognition as sr
import json
import websockets
import asyncio
import pyaudio
import wave
from datetime import datetime
import threading
import time
from anthropic import Anthropic

# Configuration - you'll need to add your Anthropic API key
API_KEY = "YOUR_ANTHROPIC_API_KEY_HERE"  
LISTEN_TIMEOUT = 5  # seconds
ENERGY_THRESHOLD = 300  # Adjust based on your microphone and environment
PAUSE_THRESHOLD = 1.0  # seconds of silence to consider the phrase complete

# Initialize Claude client
client = Anthropic(api_key=API_KEY)

# Audio setup
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 4096

# Initialize recognizer
recognizer = sr.Recognizer()
recognizer.energy_threshold = ENERGY_THRESHOLD
recognizer.pause_threshold = PAUSE_THRESHOLD

# Global state
is_listening = False
conversation_history = [{"role": "assistant", "content": "Hello! I'm Claude. How can I help you today?"}]
active_clients = set()

# Speech recognition function
def recognize_speech():
    with sr.Microphone() as source:
        print("Adjusting for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Listening...")
        
        try:
            audio = recognizer.listen(source, timeout=LISTEN_TIMEOUT)
            print("Processing speech...")
            text = recognizer.recognize_google(audio)
            print(f"Recognized: {text}")
            return text
        except sr.WaitTimeoutError:
            print("No speech detected within timeout period")
            return None
        except sr.UnknownValueError:
            print("Could not understand audio")
            return None
        except sr.RequestError as e:
            print(f"Recognition service error: {e}")
            return None

# Claude interaction function
async def ask_claude(query):
    global conversation_history
    
    # Add user message to history
    conversation_history.append({"role": "user", "content": query})
    
    try:
        # Get response from Claude
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            messages=conversation_history
        )
        
        claude_response = response.content[0].text
        
        # Add Claude's response to history
        conversation_history.append({"role": "assistant", "content": claude_response})
        
        return claude_response
    except Exception as e:
        error_message = f"Error communicating with Claude: {str(e)}"
        print(error_message)
        return error_message

# WebSocket handlers
async def register(websocket):
    print("Client connected")
    active_clients.add(websocket)
    try:
        # Send conversation history to new client
        for message in conversation_history:
            if message["role"] == "assistant":
                await websocket.send(json.dumps({
                    "type": "message",
                    "role": "assistant",
                    "content": message["content"],
                    "timestamp": datetime.now().isoformat()
                }))
        
        # Listen for messages from client
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "command" and data["command"] == "toggle_listening":
                toggle_listening()
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        active_clients.remove(websocket)

async def broadcast(message):
    if active_clients:
        await asyncio.gather(
            *[client.send(json.dumps(message)) for client in active_clients]
        )

# Voice control functions
def toggle_listening():
    global is_listening
    is_listening = not is_listening
    status = "activated" if is_listening else "deactivated"
    print(f"Voice recognition {status}")
    
    # Broadcast status change
    asyncio.create_task(broadcast({
        "type": "status",
        "listening": is_listening,
        "timestamp": datetime.now().isoformat()
    }))
    
    if is_listening:
        threading.Thread(target=voice_listener_thread, daemon=True).start()

def voice_listener_thread():
    global is_listening
    
    while is_listening:
        query = recognize_speech()
        if query and is_listening:  # Double-check is_listening in case it changed
            print(f"Sending to Claude: {query}")
            
            # Broadcast user message
            asyncio.run(broadcast({
                "type": "message",
                "role": "user",
                "content": query,
                "timestamp": datetime.now().isoformat()
            }))
            
            # Get Claude's response
            claude_response = asyncio.run(ask_claude(query))
            
            # Broadcast Claude's response
            asyncio.run(broadcast({
                "type": "message",
                "role": "assistant",
                "content": claude_response,
                "timestamp": datetime.now().isoformat()
            }))

# Main server function
async def main():
    # Start WebSocket server
    async with websockets.serve(register, "localhost", 8765):
        print("MCP Server started on ws://localhost:8765")
        
        # Keep the server running
        await asyncio.Future()

if __name__ == "__main__":
    print("Starting MCP Voice Control Server for Claude")
    print("Press Ctrl+C to exit")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down MCP server")