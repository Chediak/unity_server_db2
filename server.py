from flask import Flask, request, jsonify
import psycopg2
import datetime
import socket
import subprocess
import re
import os
from flask_cors import CORS

app = Flask(__name__)

# Define all allowed origins in one place
ALLOWED_ORIGINS = [
    "https://d2jfz0kjc1fz6i.cloudfront.net",
    "https://unity-server-db2.onrender.com",
    "http://localhost:5000",
    "http://localhost:5001",
    "http://127.0.0.1:5000",
    "http://127.0.0.1:5001"
]

# Set up CORS properly - the key is to set vary_header=True for browser caching
CORS(app, 
     resources={r"/*": {
         "origins": ALLOWED_ORIGINS,
         "methods": ["GET", "POST", "OPTIONS"],
         "allow_headers": ["Content-Type", "Authorization"],
         "expose_headers": ["Content-Type", "Authorization"],
         "supports_credentials": True
     }},
     vary_header=True)  # Important for proper CORS behavior with multiple origins

# Database connection settings
DB_HOST = "realbotix-users.czs0ek88kocm.us-east-2.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "realbotix-users"
DB_USER = "postgres"
DB_PASSWORD = "qeSkyd-myffer-cisny0"

# Function to establish a database connection
def connect_db():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Function to get Raspberry Pi's serial number
def get_raspberry_serial():
    try:
        # Check if /proc/cpuinfo exists (Linux systems)
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        return line.split(':')[1].strip()

        # Alternative method using command line
        output = subprocess.check_output(['cat', '/proc/cpuinfo']).decode('utf-8')
        for line in output.split('\n'):
            if line.startswith('Serial'):
                return line.split(':')[1].strip()

        # If methods above fail, try with vcgencmd (Raspberry Pi specific)
        output = subprocess.check_output(['vcgencmd', 'otp_dump']).decode('utf-8')
        for line in output.split('\n'):
            if line.startswith('28:'):
                return line.split(':')[1].strip()
    except Exception as e:
        print(f"Error getting serial: {e}")
        # Return a default value if we can't get the real serial
        return "UNKNOWN_SERIAL"

# Function to get Raspberry Pi's IP address
def get_ip_address():
    try:
        # Get primary IP address by creating a socket connection
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception as e:
        print(f"Error getting IP: {e}")
        # Alternative method to get IP
        try:
            # Get IP address using hostname
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            return ip_address
        except:
            # Fallback to localhost if we can't determine the IP
            return "127.0.0.1"

# Route to assign a Raspberry Pi to a user
@app.route("/assign-user", methods=["POST"])
def assign_user():
    data = request.json
    user_id = data.get("user_id")
    email = data.get("email")

    # Get Raspberry Pi serial
    serial = data.get("serial") or get_raspberry_serial()

    if not serial or not user_id or not email:
        return jsonify({"error": "Missing serial, user_id, or email"}), 400

    try:
        conn = connect_db()
        cursor = conn.cursor()

        # Ensure the device exists before updating
        cursor.execute("SELECT serial FROM devices WHERE serial = %s", (serial,))
        existing_device = cursor.fetchone()

        if existing_device:
            cursor.execute(
                "UPDATE devices SET user_id = %s, email = %s WHERE serial = %s",
                (user_id, email, serial),
            )
        else:
            cursor.execute(
                "INSERT INTO devices (serial, user_id, email, registered_at) VALUES (%s, %s, %s, %s)",
                (serial, user_id, email, datetime.datetime.now()),
            )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Raspberry assigned to user successfully!"}), 200

    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

# Route to register a device (automatically gets IP)
@app.route("/register-device", methods=["POST"])
def register_device():
    data = request.json or {}

    # Get serial and IP automatically if not provided
    serial = data.get("serial") or get_raspberry_serial()
    ip_address = data.get("ip_address") or get_ip_address()

    if not serial:
        return jsonify({"error": "Could not determine device serial number"}), 400

    try:
        conn = connect_db()
        cursor = conn.cursor()

        # Check if the device exists in the database
        cursor.execute("SELECT user_id, email FROM devices WHERE serial = %s", (serial,))
        result = cursor.fetchone()

        if result:
            user_id, email = result
            # Use ip_public or ip_address based on your database schema
            cursor.execute(
                "UPDATE devices SET ip_address = %s WHERE serial = %s",
                (ip_address, serial),
            )
        else:
            user_id, email = None, None
            # Use ip_public or ip_address based on your database schema
            cursor.execute(
                "INSERT INTO devices (serial, ip_address, registered_at) VALUES (%s, %s, %s)",
                (serial, ip_address, datetime.datetime.now()),
            )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Device registered successfully!",
            "user_id": user_id,
            "email": email,
            "serial": serial,
            "ip_address": ip_address
        }), 200

    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

# Route to check if a Raspberry Pi is already registered
@app.route("/check-device", methods=["GET"])
def check_device():
    # Get serial automatically if not provided
    serial = request.args.get("serial") or get_raspberry_serial()

    if not serial:
        return jsonify({"error": "Could not determine device serial number"}), 400

    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE serial = %s", (serial,))
        device = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        conn.close()

        if device:
            # Convert row to dictionary for better JSON response
            device_dict = dict(zip(columns, device)) if columns else {}
            return jsonify({"message": "Device is registered", "device_info": device_dict}), 200
        else:
            return jsonify({"message": "Device not found"}), 404

    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

# Route to get device information (for debugging)
@app.route("/device-info", methods=["GET"])
def device_info():
    serial = get_raspberry_serial()
    ip_address = get_ip_address()

    return jsonify({
        "serial": serial,
        "ip_address": ip_address,
        "hostname": socket.gethostname(),
        "timestamp": datetime.datetime.now().isoformat()
    }), 200

@app.route("/get-all-devices", methods=["GET"])
def get_all_devices():
    try:
        conn = connect_db()
        cursor = conn.cursor()

        # Query to get all devices with specific columns
        cursor.execute("""
            SELECT
                id,
                serial,
                ip_public AS ip_public,
                ips,
                email,
                user_id,
                registered_at,
                ip_address
            FROM devices
        """)

        devices = cursor.fetchall()

        # Get column names for better JSON formatting
        columns = [desc[0] for desc in cursor.description]

        # Convert results to a list of dictionaries
        result = []
        for device in devices:
            device_dict = dict(zip(columns, device))
            # Format datetime objects to strings for JSON serialization
            for key, value in device_dict.items():
                if isinstance(value, datetime.datetime):
                    device_dict[key] = value.isoformat()
            result.append(device_dict)

        cursor.close()
        conn.close()

        return jsonify({
            "message": "Devices retrieved successfully",
            "count": len(result),
            "devices": result
        }), 200

    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

# Add a simple health check route
@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "up",
        "message": "Server is running",
        "timestamp": datetime.datetime.now().isoformat()
    }), 200

# IMPORTANT: Remove the previous @app.after_request handler
# as it's conflicting with flask_cors

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)