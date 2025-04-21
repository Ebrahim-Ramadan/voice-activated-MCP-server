import tkinter as tk
import json
import asyncio
import websockets
import threading
from datetime import datetime
import time

class ClaudeDesktopClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Claude Desktop with Voice Control")
        self.root.geometry("800x600")
        self.websocket = None
        self.connected = False
        
        # Configure the main window
        self.root.configure(bg="#f0f0f0")
        
        # Create the chat display
        self.chat_frame = tk.Frame(root, bg="#ffffff")
        self.chat_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.chat_display = tk.Text(self.chat_frame, wrap=tk.WORD, bg="#ffffff", 
                                   font=("Arial", 12), state=tk.DISABLED)
        self.chat_display.pack(fill=tk.BOTH, expand=True)
        
        # Add a scrollbar
        scrollbar = tk.Scrollbar(self.chat_display)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.chat_display.yview)
        
        # Create the input area
        self.input_frame = tk.Frame(root, bg="#f0f0f0")
        self.input_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.text_input = tk.Entry(self.input_frame, font=("Arial", 12))
        self.text_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.text_input.bind("<Return>", self.send_message)
        
        self.send_button = tk.Button(self.input_frame, text="Send", command=self.send_message,
                                    bg="#4CAF50", fg="white", font=("Arial", 12))
        self.send_button.pack(side=tk.LEFT)
        
        # Create voice control button
        self.voice_button_frame = tk.Frame(root, bg="#f0f0f0")
        self.voice_button_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.voice_status = tk.Label(self.voice_button_frame, text="Voice Recognition: OFF",
                                   font=("Arial", 12), fg="#D32F2F", bg="#f0f0f0")
        self.voice_status.pack(side=tk.LEFT, padx=(0, 10))
        
        self.voice_button = tk.Button(self.voice_button_frame, text="Toggle Voice Recognition",
                                    command=self.toggle_voice_recognition,
                                    bg="#2196F3", fg="white", font=("Arial", 12))
        self.voice_button.pack(side=tk.LEFT)
        
        # Connection status
        self.connection_status = tk.Label(root, text="Disconnected", 
                                        font=("Arial", 10), fg="#D32F2F", bg="#f0f0f0")
        self.connection_status.pack(anchor=tk.W, padx=20, pady=5)
        
        # Start connection
        self.connect_thread = threading.Thread(target=self.start_connection, daemon=True)
        self.connect_thread.start()
    
    def start_connection(self):
        """Start the WebSocket connection in a separate thread"""
        asyncio.run(self.connect_websocket())
    
    async def connect_websocket(self):
        """Connect to the WebSocket server"""
        while True:
            try:
                self.update_connection_status("Connecting...", "#FFA000")
                async with websockets.connect("ws://localhost:8765") as websocket:
                    self.websocket = websocket
                    self.connected = True
                    self.update_connection_status("Connected", "#4CAF50")
                    
                    # Listen for messages from the server
                    while True:
                        message = await websocket.recv()
                        self.handle_server_message(message)
                        
            except (websockets.exceptions.ConnectionClosed, 
                   websockets.exceptions.InvalidStatusCode,
                   ConnectionRefusedError) as e:
                self.connected = False
                self.update_connection_status(f"Disconnected: {str(e)}", "#D32F2F")
                # Wait before trying to reconnect
                await asyncio.sleep(5)
    
    def update_connection_status(self, text, color):
        """Update the connection status text and color"""
        self.root.after(0, lambda: self.connection_status.config(text=text, fg=color))
    
    def handle_server_message(self, message_json):
        """Handle incoming messages from the server"""
        message = json.loads(message_json)
        
        if message["type"] == "message":
            # Display the message
            self.root.after(0, lambda: self.display_message(
                message["role"], message["content"], message["timestamp"]))
        
        elif message["type"] == "status":
            # Update voice recognition status
            status = "ON" if message["listening"] else "OFF"
            color = "#4CAF50" if message["listening"] else "#D32F2F"
            self.root.after(0, lambda: self.voice_status.config(
                text=f"Voice Recognition: {status}", fg=color))
    
    def display_message(self, role, content, timestamp):
        """Display a message in the chat window"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Format timestamp
        dt = datetime.fromisoformat(timestamp)
        time_str = dt.strftime("%H:%M:%S")
        
        # Set tag for formatting
        role_tag = "user" if role == "user" else "assistant"
        self.chat_display.tag_config("user", foreground="#2196F3", font=("Arial", 10, "bold"))
        self.chat_display.tag_config("assistant", foreground="#4CAF50", font=("Arial", 10, "bold"))
        self.chat_display.tag_config("time", foreground="#9E9E9E", font=("Arial", 8))
        
        # Insert the message
        self.chat_display.insert(tk.END, f"{role.capitalize()} ", role_tag)
        self.chat_display.insert(tk.END, f"[{time_str}]:\n", "time")
        self.chat_display.insert(tk.END, f"{content}\n\n")
        
        # Scroll to the bottom
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
    
    def send_message(self, event=None):
        """Send a text message to the server"""
        message = self.text_input.get().strip()
        if not message or not self.connected:
            return
        
        # Clear the input field
        self.text_input.delete(0, tk.END)
        
        # Display the message locally
        self.display_message("user", message, datetime.now().isoformat())
        
        # Send the message to the server
        if self.websocket and self.connected:
            asyncio.run(self.send_to_server(message))
    
    async def send_to_server(self, text_message):
        """Send a message to the WebSocket server"""
        try:
            message = {
                "type": "message",
                "content": text_message,
                "timestamp": datetime.now().isoformat()
            }
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def toggle_voice_recognition(self):
        """Toggle voice recognition on/off"""
        if not self.connected:
            return
            
        asyncio.run(self.send_toggle_command())
    
    async def send_toggle_command(self):
        """Send the toggle voice command to the server"""
        try:
            command = {
                "type": "command",
                "command": "toggle_listening",
                "timestamp": datetime.now().isoformat()
            }
            await self.websocket.send(json.dumps(command))
        except Exception as e:
            print(f"Error sending toggle command: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ClaudeDesktopClient(root)
    root.mainloop()