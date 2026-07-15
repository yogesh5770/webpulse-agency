
import sys
from agent_router import chat, test_connection

print("Testing Bedrock integration...")

# First test the connection
print("\n--- Testing all connections ---")
success, msg = test_connection()
print(msg)

if not success:
    print("\nNo working AI providers found.")
    sys.exit(1)

# Test a simple chat
print("\n--- Testing simple chat ---")
try:
    response = chat([{"role": "user", "content": "Hello, what's your name?"}], max_tokens=100)
    print("Response:", response.get("content"))
except Exception as e:
    print(f"Error during chat test: {e}")
    import traceback
    traceback.print_exc()

