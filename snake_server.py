"""Authoritative multiplayer Snake server.

Accepts TCP connections from any number of clients, exchanges an RSA
key pair with each one, and runs the shared SnakeGame on a fixed tick
in a background thread, broadcasting the resulting game state to
every connected client.
"""

import socket
import time
import uuid
from _thread import start_new_thread

import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from snake import SnakeGame


def client_thread(conn, unique_id):
    """Handle one client connection: key exchange, then the recv/respond
    loop for moves, resets, chat messages, and quit.
    """
    global game, moves_queue, game_state, clients, clients_public_keys, server_public_key

    try:
        # Receive and deserialize the client's public key
        client_public_key_pem = recv_all(conn)
        client_public_key = serialization.load_pem_public_key(client_public_key_pem)
        clients_public_keys[unique_id] = client_public_key
        print(f"Received public key from client {unique_id}")

        # Serialize and send the server's public key to the client
        conn.send(server_public_key)
        print(f"Sent server's public key to client {unique_id}")

        # Send initial game state
        conn.send(game_state.encode())

        while True:
            try:
                data = conn.recv(500).decode()
                if not data:
                    print("Client disconnected")
                    break

                elif data == "get":
                    pass  # Handle 'get' command
                elif data == "quit":
                    print(f"Client {unique_id} quit")
                    game.remove_player(unique_id)
                    break
                elif data == "reset":
                    game.reset_player(unique_id)
                elif data in ["up", "down", "left", "right"]:
                    moves_queue.add((unique_id, data))
                else:
                    broadcast_message(data, unique_id)
                # Send updated game state
                conn.send(game_state.encode())

            except Exception as inner_e:
                print(f"Error during message handling for client {unique_id}: {inner_e}")

    except Exception as e:
        print(f"Error during key exchange with client {unique_id}: {e}")

    finally:
        # Clean up when the client disconnects or an error occurs
        conn.close()
        if unique_id in clients:
            del clients[unique_id]
        if unique_id in clients_public_keys:
            del clients_public_keys[unique_id]


def recv_all(sock, buffer_size=4096):
    """Read from sock until a short (or empty) chunk signals end of data."""
    data = b''
    while True:
        part = sock.recv(buffer_size)
        data += part
        if len(part) < buffer_size:
            # Either end of data or buffer wasn't filled; in both cases, break
            break
    return data


def generate_rsa_key_pair():
    """Generate a fresh RSA key pair, returning (private_pem, public_pem)."""
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate public key
    public_key = private_key.public_key()

    # Serialize the private key to PEM format
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize the public key to PEM format
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return pem_private, pem_public


def broadcast_message(message, sender_id):
    """Relay a chat message from sender_id to every other connected client."""
    print(f"Recieved message: {message}")
    formatted_message = f"user {sender_id}: {message}"  # Format the message
    for unique_id, conn in clients.items():
        if unique_id != sender_id:  # Do not send the message back to the sender
            try:
                conn.send(formatted_message.encode())  # Send the formatted message
            except Exception as e:
                print(f"Error broadcasting message to {unique_id}: {e}")


def game_thread():
    """Background loop: advance the game one tick every `interval` seconds."""
    global game, moves_queue, game_state
    while True:
        last_move_timestamp = time.time()
        game.move(moves_queue)
        moves_queue = set()
        game_state = game.get_state()
        while time.time() - last_move_timestamp < interval:
            time.sleep(0.1)


def run_server(s, server_port):
    """Start the game loop thread, then accept clients forever."""
    start_new_thread(game_thread, ())

    while True:
        conn, addr = s.accept()
        print("Connected to:", addr)

        unique_id = str(uuid.uuid4())
        color = rgb_colors_list[np.random.randint(0, len(rgb_colors_list))]
        game.add_player(unique_id, color=color)
        clients[unique_id] = conn
        ct = start_new_thread(client_thread, (conn, unique_id))
        client_threads.append(ct)


if __name__ == "__main__":
    # Generate the server's RSA key pair
    server_private_key_pem, server_public_key = generate_rsa_key_pair()
    server_private_key = serialization.load_pem_private_key(
        server_private_key_pem,
        password=None
    )
    print("Server's RSA key pair generated.")

    # Server setup
    server = "localhost"
    port = 5555
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clients = {}
    clients_public_keys = {}
    try:
        soc.bind((server, port))
    except socket.error as e:
        print(str(e))

    soc.listen()
    print("Waiting for a connection, Server Started")

    rgb_colors = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "orange": (255, 165, 0),
    }
    rgb_colors_list = list(rgb_colors.values())

    # Game setup
    game = SnakeGame(20)
    game_state = ""
    interval = 0.2
    moves_queue = set()
    client_threads = []

    run_server(soc, port)
