# OneCAdapter.py
import json
import time
import logging
import os
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ----------------------------

# Import RabbitMQClient after logging setup to ensure it uses the same logger
from rabbitmq import RabbitMQClient

# --- Flask application for receiving HTTP requests from 1C ---
app = Flask(__name__)
rabbitmq_client_instance = None # Will be initialized upon startup

@app.route('/send_to_dms', methods=['POST'])
def send_to_dms():
    """
    Handles HTTP POST requests from 1C to send data to the DMS system.
    Publishes the received data as a message to RabbitMQ.
    """
    global rabbitmq_client_instance
    if rabbitmq_client_instance is None or not rabbitmq_client_instance.channel:
        logger.error("RabbitMQ client not initialized or channel not open for /send_to_dms.")
        return jsonify({"status": "error", "message": "RabbitMQ client not initialized"}), 500

    try:
        # 1C sends JSON in the request body
        data_from_1c = request.get_json()
        if not data_from_1c:
            logger.warning("Received empty or invalid JSON data from 1C for /send_to_dms.")
            return jsonify({"status": "error", "message": "Invalid JSON data"}), 400

        # Formulate the message for RabbitMQ
        message = {
            "source_system": "1C",
            "target_system": "DMS",
            "message_type": "create_user", # Or another type, based on the 1C request
            "payload": data_from_1c, # Data received from 1C
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": data_from_1c.get("request_id", f"1C_{int(time.time())}") # For tracking responses
        }

        routing_key = "1c.request.dms.create_user" # or dynamically generated

        if rabbitmq_client_instance.publish_message(rabbitmq_client_instance.exchange_name, routing_key, message):
            logger.info(f"[1C Adapter] Received from 1C and published to RabbitMQ: {message}")
            return jsonify({"status": "success", "message": "Message sent to DMS via RabbitMQ"}), 200
        else:
            logger.error("[1C Adapter] Failed to publish message to RabbitMQ for /send_to_dms.")
            return jsonify({"status": "error", "message": "Failed to publish message to RabbitMQ"}), 500
    except Exception as e:
        logger.exception(f"[1C Adapter] Error processing 1C request for /send_to_dms: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/send_to_crm', methods=['POST'])
def send_to_crm():
    """
    Handles HTTP POST requests from 1C to send data to the CRM system.
    Publishes the received data as a message to RabbitMQ.
    """
    global rabbitmq_client_instance
    if rabbitmq_client_instance is None or not rabbitmq_client_instance.channel:
        logger.error("RabbitMQ client not initialized or channel not open for /send_to_crm.")
        return jsonify({"status": "error", "message": "RabbitMQ client not initialized"}), 500

    try:
        data_from_1c = request.get_json()
        if not data_from_1c:
            logger.warning("Received empty or invalid JSON data from 1C for /send_to_crm.")
            return jsonify({"status": "error", "message": "Invalid JSON data"}), 400

        message = {
            "source_system": "1C",
            "target_system": "CRM",
            "message_type": "update_order_status",
            "payload": data_from_1c,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": data_from_1c.get("request_id", f"1C_{int(time.time())}")
        }

        routing_key = "1c.request.crm.update_order_status"

        if rabbitmq_client_instance.publish_message(rabbitmq_client_instance.exchange_name, routing_key, message):
            logger.info(f"[1C Adapter] Received from 1C and published to RabbitMQ: {message}")
            return jsonify({"status": "success", "message": "Message sent to CRM via RabbitMQ"}), 200
        else:
            logger.error("[1C Adapter] Failed to publish message to RabbitMQ for /send_to_crm.")
            return jsonify({"status": "error", "message": "Failed to publish message to RabbitMQ"}), 500
    except Exception as e:
        logger.exception(f"[1C Adapter] Error processing 1C request for /send_to_crm: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- Class for handling responses from RabbitMQ for 1C ---
class ICListener(RabbitMQClient):
    """
    ICListener consumes messages from the '1c_queue' which are responses from
    other systems (DMS, CRM) intended for 1C.
    """
    def __init__(self):
        super().__init__() # Call without parameters, they are taken from .env
        self.ic_queue_name = '1c_queue' # Queue for messages intended for 1C
        self.ic_dl_exchange = '1c_dlx' # DLX for 1C
        self.ic_dl_queue = '1c_dead_letter_queue' # DL-queue for 1C
        self.connect()
        if self.channel:
            self.declare_exchange(self.exchange_name, 'topic')
            # Declare DLX and DL-queue for 1C
            self.declare_dead_letter_queue_and_exchange(self.ic_dl_queue, self.ic_dl_exchange)
            # Declare the main 1C queue, binding it to the DLX
            self.declare_queue(self.ic_queue_name, self.ic_dl_exchange, '1c.dead_letter')

            # Bind the 1C queue to all messages directed to 1C (i.e., responses from other systems)
            self.bind_queue(self.ic_queue_name, self.exchange_name, "dms.response.1c.#")
            self.bind_queue(self.ic_queue_name, self.exchange_name, "crm.response.1c.#")
            logger.info(f"1C Listener is listening for messages on queue '{self.ic_queue_name}'.")

    def _process_message(self, ch, method, properties, body):
        """
        Callback function to process incoming messages for the 1C listener.
        Handles message deserialization, retries, and simulates actions for 1C.
        """
        MAX_RETRIES = 3 # Maximum number of message processing attempts
        try:
            message = json.loads(body)
            logger.info(f"\n[1C Adapter Listener] Received message for 1C: {message}")

            # Add or increment retry counter
            retries = message.get('retries', 0)
            message['retries'] = retries + 1

            # --- ACTUAL ACTION IN 1C (or preparation for 1C) ---
            # Here, the received data would typically be written to a database,
            # file, or an internal 1C API expecting this response would be called.
            # For example, the response could be saved to a DB that 1C periodically polls.
            source_system = message.get("source_system")
            message_type = message.get("message_type")
            payload = message.get("payload")
            request_id = message.get("request_id") # Use request_id to link request and response

            if source_system == "DMS" and message_type == "user_created_response":
                logger.info(f"[1C Adapter Listener] User created in DMS: {payload}. Updating 1C data for request_id: {request_id}...")
                # Example: API_1C.update_user_status(payload['user_id'], payload['status'], payload['dms_id'])
                # Or saving to a file/DB that 1C monitors.
                # if payload.get("status") == "success":
                #     self.save_to_1c_db_or_file(request_id, payload)
                # else:
                #     self.log_1c_error(request_id, payload)
                logger.info(f"[1C Adapter Listener] Notifying 1C about user creation result for request_id: {request_id}")

            elif source_system == "CRM" and message_type == "order_status_updated_response":
                logger.info(f"[1C Adapter Listener] Order status updated in CRM: {payload}. Updating 1C data for request_id: {request_id}...")
                # Example: API_1C.update_order_status(payload['order_id'], payload['new_status'])
                # self.save_to_1c_db_or_file(request_id, payload)
                logger.info(f"[1C Adapter Listener] Notifying 1C about order status update for request_id: {request_id}")

            else:
                logger.warning(f"[1C Adapter Listener] Unhandled message type or source system: {message_type} from {source_system}. Message: {message}")
                # If the message cannot be processed, it should be rejected.
                # If the message type is not recognized, it might be an error, send to DLX
                self.nack_message(method, requeue=False) # Negative acknowledgment, do not re-queue
                return # Exit to avoid acknowledging the message

            self.acknowledge_message(method) # Acknowledge successful processing

        except json.JSONDecodeError:
            logger.error(f"[1C Adapter Listener] Error: Invalid JSON received, rejecting message: {body.decode()}", exc_info=True)
            self.reject_message(method, requeue=False) # Reject message, do not re-queue
        except Exception as e:
            logger.exception(f"[1C Adapter Listener] Unhandled error processing message (attempt {message.get('retries', 1)}/{MAX_RETRIES}): {e}")
            if message['retries'] < MAX_RETRIES:
                # If attempts are below the limit, re-queue for a retry
                self.nack_message(method, requeue=True)
            else:
                logger.critical(f"[1C Adapter Listener] Message failed after {MAX_RETRIES} attempts, sending to DLX: {message}")
                self.nack_message(method, requeue=False) # Send to DLX

    def start(self):
        """
        Starts the 1C Listener consumer to process messages from its queue.
        """
        if self.channel:
            logger.info("Starting 1C Listener consumer...")
            self.start_consuming(self.ic_queue_name, self._process_message)
        else:
            logger.error("Failed to initialize 1C Listener. Check RabbitMQ connection.")

# --- Start Flask service and RabbitMQ listener in separate threads/processes ---
if __name__ == "__main__":
    rabbitmq_client_instance = RabbitMQClient()
    rabbitmq_client_instance.connect()
    if rabbitmq_client_instance.connection and rabbitmq_client_instance.channel:
        rabbitmq_client_instance.declare_exchange(rabbitmq_client_instance.exchange_name, 'topic') # Declare the main exchange

        # Start the RabbitMQ listener in a separate thread
        listener = ICListener()
        listener_thread = threading.Thread(target=listener.start)
        listener_thread.daemon = True # Make the thread a daemon so it exits when the main program closes
        listener_thread.start()

        # Start the Flask application
        flask_port = int(os.getenv('FLASK_PORT', 5000))
        logger.info(f"Starting 1C Flask HTTP server on http://0.0.0.0:{flask_port}") # 0.0.0.0 for Docker access
        app.run(debug=False, host='0.0.0.0', port=flask_port) # In production, use Gunicorn/Waitress

    else:
        logger.critical("Failed to start 1C Adapter (RabbitMQ connection error). Exiting.")

    if rabbitmq_client_instance:
        rabbitmq_client_instance.close()