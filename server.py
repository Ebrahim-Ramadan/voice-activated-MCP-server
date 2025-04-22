import speech_recognition as sr
import threading
import time
import tkinter as tk
from tkinter import scrolledtext
import queue
import inspect
from typing import List, Dict, Any, Callable, Optional, Union

# Simple implementation of FastMCP-like functionality
class SimpleMCP:
    def __init__(self, name: str):
        self.name = name
        self.tools = {}
        self.resources = {}
        self.resource_patterns = {}
    
    def tool(self):
        """Decorator to register a function as a tool"""
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator
    
    def resource(self, pattern: str):
        """Decorator to register a function as a resource"""
        def decorator(func):
            # Extract the variable pattern from the URL pattern
            # e.g., "greeting://{name}" -> "name"
            import re
            var_pattern = re.search(r'{(\w+)}', pattern)
            if var_pattern:
                var_name = var_pattern.group(1)
                resource_name = pattern.split('://')[0]
                self.resource_patterns[resource_name] = (func, var_name)
            self.resources[pattern] = func
            return func
        return decorator
    
    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """Execute a registered tool with given parameters"""
        if tool_name in self.tools:
            tool_func = self.tools[tool_name]
            # Get the required parameters for the function
            sig = inspect.signature(tool_func)
            params = {}
            for param_name, param in sig.parameters.items():
                if param_name in kwargs:
                    params[param_name] = kwargs[param_name]
            
            # Execute the function with the parameters
            return tool_func(**params)
        return f"Tool '{tool_name}' not found."
    
    def execute_resource(self, resource_pattern: str, **kwargs) -> str:
        """Execute a registered resource with given parameters"""
        for pattern, func in self.resources.items():
            # Check if the pattern matches
            if pattern.split('://')[0] == resource_pattern:
                # Extract parameters from the pattern
                sig = inspect.signature(func)
                params = {}
                for param_name, param in sig.parameters.items():
                    if param_name in kwargs:
                        params[param_name] = kwargs[param_name]
                
                # Execute the function with the parameters
                return func(**params)
        
        # Try resource patterns
        if resource_pattern in self.resource_patterns:
            func, var_name = self.resource_patterns[resource_pattern]
            if var_name in kwargs:
                return func(kwargs[var_name])
        
        return f"Resource '{resource_pattern}' not found."
    
    def run(self):
        """Run the MCP server"""
        print(f"{self.name} MCP Server is running...")

# In-memory mock database with leave days
employee_leaves = {
    "E001": {"balance": 18, "history": ["2024-12-25", "2025-01-01"]},
    "E002": {"balance": 20, "history": []}
}

# Create message queue for communication between threads
message_queue = queue.Queue()

# Create MCP server
mcp = SimpleMCP("LeaveManager")

# Tool: Check Leave Balance
@mcp.tool()
def get_leave_balance(employee_id: str) -> str:
    """Check how many leave days are left for the employee"""
    data = employee_leaves.get(employee_id)
    if data:
        return f"{employee_id} has {data['balance']} leave days remaining."
    return "Employee ID not found."

# Tool: Apply for Leave with specific dates
@mcp.tool()
def apply_leave(employee_id: str, leave_dates: List[str]) -> str:
    """
    Apply leave for specific dates (e.g., ["2025-04-17", "2025-05-01"])
    """
    if employee_id not in employee_leaves:
        return "Employee ID not found."
    requested_days = len(leave_dates)
    available_balance = employee_leaves[employee_id]["balance"]
    if available_balance < requested_days:
        return f"Insufficient leave balance. You requested {requested_days} day(s) but have only {available_balance}."
    # Deduct balance and add to history
    employee_leaves[employee_id]["balance"] -= requested_days
    employee_leaves[employee_id]["history"].extend(leave_dates)
    return f"Leave applied for {requested_days} day(s). Remaining balance: {employee_leaves[employee_id]['balance']}."

# Resource: Leave history
@mcp.tool()
def get_leave_history(employee_id: str) -> str:
    """Get leave history for the employee"""
    data = employee_leaves.get(employee_id)
    if data:
        history = ', '.join(data['history']) if data['history'] else "No leaves taken."
        return f"Leave history for {employee_id}: {history}"
    return "Employee ID not found."

# Resource: Greeting
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}! How can I assist you with leave management today?"

# Voice recognition function
def voice_recognizer(stop_event, recognizer_active):
    """Thread function to handle voice recognition"""
    # Initialize recognizer
    r = sr.Recognizer()
    r.energy_threshold = 300  # Adjust based on environment
    r.pause_threshold = 1.0

    # Put initial message in queue
    message_queue.put({
        "source": "system",
        "content": "Voice recognition system initialized. Say something to get started."
    })

    while not stop_event.is_set():
        # Only listen when recognition is active
        if recognizer_active.is_set():
            try:
                with sr.Microphone() as source:
                    message_queue.put({
                        "source": "system",
                        "content": "Listening..."
                    })
                    
                    # Adjust for ambient noise
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    
                    # Listen for input
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)
                    
                    message_queue.put({
                        "source": "system",
                        "content": "Processing speech..."
                    })
                    
                    # Use Google's speech recognition
                    text = r.recognize_google(audio)
                    
                    # Put recognized text in queue
                    message_queue.put({
                        "source": "user",
                        "content": text
                    })
                    
                    # Process the command through MCP
                    response = process_voice_command(text)
                    
                    # Put MCP response in queue
                    message_queue.put({
                        "source": "mcp",
                        "content": response
                    })
                    
            except sr.WaitTimeoutError:
                message_queue.put({
                    "source": "system",
                    "content": "Listening timed out. Please try again."
                })
            except sr.UnknownValueError:
                message_queue.put({
                    "source": "system", 
                    "content": "Sorry, I couldn't understand what you said."
                })
            except sr.RequestError as e:
                message_queue.put({
                    "source": "system",
                    "content": f"Speech recognition service error: {e}"
                })
            except Exception as e:
                message_queue.put({
                    "source": "system",
                    "content": f"Error: {str(e)}"
                })
        else:
            # Sleep to prevent CPU hogging when not listening
            time.sleep(0.5)

def process_voice_command(command):
    """Process voice commands and route to appropriate MCP functions"""
    command = command.lower()
    
    # Handle check balance commands
    if "balance" in command or "how many days" in command:
        # Extract employee ID - assuming format like "check balance for E001"
        for emp_id in employee_leaves.keys():
            if emp_id.lower() in command:
                return mcp.execute_tool("get_leave_balance", employee_id=emp_id)
        return "Please specify a valid employee ID like E001 or E002."
    
    # Handle leave history commands
    elif "history" in command:
        for emp_id in employee_leaves.keys():
            if emp_id.lower() in command:
                return mcp.execute_tool("get_leave_history", employee_id=emp_id)
        return "Please specify a valid employee ID like E001 or E002."
    
    # Handle leave application - this is more complex and might require a conversation
    elif "apply" in command and "leave" in command:
        try:
            # Extract employee ID
            emp_id = None
            for e_id in employee_leaves.keys():
                if e_id.lower() in command:
                    emp_id = e_id
                    break
            
            if not emp_id:
                return "Please specify a valid employee ID like E001 or E002."
            
            # Try to extract dates - assuming format like "2025-04-17"
            import re
            dates = re.findall(r'\d{4}-\d{2}-\d{2}', command)
            
            if not dates:
                return "I couldn't identify any dates in your request. Please specify dates in YYYY-MM-DD format."
            
            return mcp.execute_tool("apply_leave", employee_id=emp_id, leave_dates=dates)
        except Exception as e:
            return f"Error processing leave application: {str(e)}"
    
    # Handle greeting
    elif "hello" in command or "hi" in command:
        # Try to extract name
        name = "there"  # Default
        name_indicators = ["my name is", "i am", "call me"]
        for indicator in name_indicators:
            if indicator in command:
                name = command.split(indicator)[1].strip().split()[0]  # Get first word after indicator
                break
        
        return mcp.execute_resource("greeting", name=name)
    
    # Handle help
    elif "help" in command:
        return """
        Available commands:
        - Check balance for [employee ID]
        - Get leave history for [employee ID]
        - Apply leave for [employee ID] on [date]
        - Hello/Hi
        """
    
    else:
        return "I'm not sure how to handle that request. Try asking for help to see available commands."

class VoiceMCPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice-Controlled MCP Leave Manager")
        self.root.geometry("800x600")
        
        # Create stop event for clean thread termination
        self.stop_event = threading.Event()
        self.recognizer_active = threading.Event()
        
        # Create UI elements
        self.create_widgets()
        
        # Start voice recognition thread
        self.voice_thread = threading.Thread(
            target=voice_recognizer, 
            args=(self.stop_event, self.recognizer_active),
            daemon=True
        )
        self.voice_thread.start()
        
        # Start message processing
        self.process_messages()
        
    def create_widgets(self):
        # Create frame for conversation display
        conversation_frame = tk.Frame(self.root)
        conversation_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Text area for conversation
        self.conversation = scrolledtext.ScrolledText(
            conversation_frame, 
            wrap=tk.WORD,
            font=("Arial", 12)
        )
        self.conversation.pack(fill=tk.BOTH, expand=True)
        self.conversation.config(state=tk.DISABLED)
        
        # Create frame for control buttons
        control_frame = tk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Toggle voice recognition button
        self.toggle_button = tk.Button(
            control_frame,
            text="Start Listening",
            command=self.toggle_recognition,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 12),
            width=15,
            height=2
        )
        self.toggle_button.pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_label = tk.Label(
            control_frame,
            text="Voice Recognition: OFF",
            font=("Arial", 12),
            fg="#D32F2F",
        )
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Text input for manual commands
        input_frame = tk.Frame(self.root)
        input_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.text_input = tk.Entry(input_frame, font=("Arial", 12))
        self.text_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.text_input.bind("<Return>", self.send_text_command)
        
        send_button = tk.Button(
            input_frame, 
            text="Send", 
            command=self.send_text_command,
            bg="#2196F3", 
            fg="white", 
            font=("Arial", 12)
        )
        send_button.pack(side=tk.RIGHT)
        
        # Help button
        help_button = tk.Button(
            control_frame,
            text="Help",
            command=self.show_help,
            bg="#FFA000",
            fg="white",
            font=("Arial", 12),
            width=10,
            height=2
        )
        help_button.pack(side=tk.RIGHT, padx=5)
        
    def toggle_recognition(self):
        if self.recognizer_active.is_set():
            self.recognizer_active.clear()
            self.toggle_button.config(text="Start Listening", bg="#4CAF50")
            self.status_label.config(text="Voice Recognition: OFF", fg="#D32F2F")
            self.add_message("System", "Voice recognition deactivated.")
        else:
            self.recognizer_active.set()
            self.toggle_button.config(text="Stop Listening", bg="#D32F2F")
            self.status_label.config(text="Voice Recognition: ON", fg="#4CAF50")
            self.add_message("System", "Voice recognition activated.")
            
    def add_message(self, sender, message):
        self.conversation.config(state=tk.NORMAL)
        
        # Format based on sender
        if sender == "User":
            self.conversation.insert(tk.END, f"You: ", "user_tag")
            self.conversation.tag_config("user_tag", foreground="#2196F3", font=("Arial", 12, "bold"))
        elif sender == "MCP":
            self.conversation.insert(tk.END, f"MCP: ", "mcp_tag")
            self.conversation.tag_config("mcp_tag", foreground="#4CAF50", font=("Arial", 12, "bold"))
        else:  # System
            self.conversation.insert(tk.END, f"System: ", "system_tag")
            self.conversation.tag_config("system_tag", foreground="#9E9E9E", font=("Arial", 12, "italic"))
        
        # Insert the message and scroll to see it
        self.conversation.insert(tk.END, f"{message}\n\n")
        self.conversation.see(tk.END)
        self.conversation.config(state=tk.DISABLED)
            
    def process_messages(self):
        """Process messages from the queue and update UI"""
        try:
            while not message_queue.empty():
                message = message_queue.get_nowait()
                
                if message["source"] == "user":
                    self.add_message("User", message["content"])
                elif message["source"] == "mcp":
                    self.add_message("MCP", message["content"])
                elif message["source"] == "system":
                    self.add_message("System", message["content"])
        except Exception as e:
            print(f"Error processing message: {e}")
            
        # Schedule next check
        self.root.after(100, self.process_messages)
        
    def send_text_command(self, event=None):
        """Process text commands from the input field"""
        command = self.text_input.get().strip()
        if command:
            # Clear input field
            self.text_input.delete(0, tk.END)
            
            # Put command in queue
            message_queue.put({
                "source": "user",
                "content": command
            })
            
            # Process command
            response = process_voice_command(command)
            
            # Put response in queue
            message_queue.put({
                "source": "mcp",
                "content": response
            })
            
    def show_help(self):
        """Show help information"""
        help_text = """
Available Commands:
------------------
- "Check balance for E001" - View remaining leave days
- "Get leave history for E001" - View taken leaves
- "Apply leave for E001 on 2025-04-25" - Request leave
- "Hello" - Get a greeting
- "Help" - Show this help message

Tips:
-----
- Speak clearly and at a moderate pace
- Mention the employee ID clearly (E001 or E002)
- For dates, use YYYY-MM-DD format
- You can also type commands in the text box below
        """
        
        message_queue.put({
            "source": "system",
            "content": help_text
        })
        
    def on_closing(self):
        """Handle window close event"""
        self.stop_event.set()  # Signal threads to stop
        self.root.destroy()

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
    
    # Start the GUI application
    root = tk.Tk()
    app = VoiceMCPApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()