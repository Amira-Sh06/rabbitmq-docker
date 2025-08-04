import json
import time
import logging
import os
import threading
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ----------------------------

from rabbitmq import RabbitMQClient

# --- Flask App and SQLite Configuration ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/1c_responses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class ICResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    response_payload = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(255), nullable=False)
    is_processed = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<ICResponse {self.request_id}>"


rabbitmq_client_instance = None


@app.route('/send_to_dms', methods=['POST'])
def send_to_dms():
    """
    API endpoint for 1C to send a 'create user' request to DMS.
    This request is published to RabbitMQ.
    """
    global rabbitmq_client_instance
    if rabbitmq_client_instance is None or not rabbitmq_client_instance.channel:
        logger.error("RabbitMQ client not initialized or channel not open for /send_to_dms.")
        return jsonify({"status": "error", "message": "RabbitMQ client not initialized"}), 500

    try:
        data_from_1c = request.get_json()
        if not data_from_1c:
            logger.warning("Received empty or invalid JSON data from 1C for /send_to_dms.")
            return jsonify({"status": "error", "message": "Invalid JSON data"}), 400

        message = {
            "source_system": "1C",
            "target_system": "DMS",
            "message_type": "create_user",
            "payload": data_from_1c,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": data_from_1c.get("request_id", f"1C_{int(time.time())}")
        }

        routing_key = "1c.request.dms.create_user"
        if rabbitmq_client_instance.publish_message(rabbitmq_client_instance.exchange_name, routing_key, message):
            logger.info(f"[1C Adapter] Received from 1C and published to RabbitMQ: {message}")
            return jsonify({"status": "success", "message": "Message sent to DMS via RabbitMQ",
                            "request_id": message["request_id"]}), 202
        else:
            logger.error("[1C Adapter] Failed to publish message to RabbitMQ for /send_to_dms.")
            return jsonify({"status": "error", "message": "Failed to publish message to RabbitMQ"}), 500
    except Exception as e:
        logger.exception(f"[1C Adapter] Error processing 1C request for /send_to_dms: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/send_to_crm', methods=['POST'])
def send_to_crm():
    """
    API endpoint for 1C to send an 'update order status' request to CRM.
    This request is published to RabbitMQ.
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
            return jsonify({"status": "success", "message": "Message sent to CRM via RabbitMQ",
                            "request_id": message["request_id"]}), 202
        else:
            logger.error("[1C Adapter] Failed to publish message to RabbitMQ for /send_to_crm.")
            return jsonify({"status": "error", "message": "Failed to publish message to RabbitMQ"}), 500
    except Exception as e:
        logger.exception(f"[1C Adapter] Error processing 1C request for /send_to_crm: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def consume_responses():
    """
    Thread function to consume messages from the 1C response queue.
    """
    global rabbitmq_client_instance
    if rabbitmq_client_instance is None:
        logger.error("RabbitMQ client not initialized for response consumer.")
        return

    def callback(ch, method, properties, body):
        try:
            response_message = json.loads(body)
            logger.info(f"\n[1C Adapter] Received response: {response_message}")

            # Extract relevant information
            request_id = response_message.get("request_id")
            if not request_id:
                logger.warning("Response message is missing 'request_id'. Rejecting.")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return

            # Store the response in the database
            with app.app_context():
                new_response = ICResponse(
                    request_id=request_id,
                    response_payload=json.dumps(response_message),
                    timestamp=response_message.get("timestamp")
                )
                db.session.add(new_response)
                db.session.commit()

            logger.info(f"Response for request '{request_id}' saved to database.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message. Error: {e}. Rejecting.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"An unexpected error occurred in response consumer: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    queue_name = '1c_queue'
    if rabbitmq_client_instance.channel:
        rabbitmq_client_instance.channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=False
        )
        logger.info(f"1C Adapter is waiting for responses on queue '{queue_name}'.")
        rabbitmq_client_instance.channel.start_consuming()


def run_flask_app():
    """
    Function to run the Flask application.
    """
    port = int(os.getenv('FLASK_PORT', 5000))
    # The debug flag is useful for development but should be False in production
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    with app.app_context():
        # Create database tables if they don't exist
        db.create_all()

    # Create and connect the RabbitMQ client
    rabbitmq_client_instance = RabbitMQClient()
    rabbitmq_client_instance.connect()

    if rabbitmq_client_instance.channel:
        # Declare necessary exchanges and queues for 1C
        rabbitmq_client_instance.declare_exchange(rabbitmq_client_instance.exchange_name, 'topic')
        dl_exchange = '1c_dlx'
        dl_queue = '1c_dead_letter_queue'
        queue_name = '1c_queue'
        rabbitmq_client_instance.declare_dead_letter_queue_and_exchange(dl_queue, dl_exchange)
        rabbitmq_client_instance.declare_queue(queue_name, dl_exchange, '1c.dead_letter')
        rabbitmq_client_instance.bind_queue(queue_name, rabbitmq_client_instance.exchange_name, "dms.response.1c.#")
        rabbitmq_client_instance.bind_queue(queue_name, rabbitmq_client_instance.exchange_name, "crm.response.1c.#")

        # Start the RabbitMQ consumer in a separate thread
        consumer_thread = threading.Thread(target=consume_responses, daemon=True)
        consumer_thread.start()

    # Run the Flask app
    run_flask_app()
