"""Pygame-based client for multiplayer Snake.

Connects to the server, exchanges an RSA key pair, then runs two
background threads (heartbeat + state receiver) alongside the main
pygame loop that reads keyboard input and renders the latest game
state sent by the server.
"""

import socket
import threading
import time

import pygame
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class SnakeClient:

    def __init__(self, server_ip, server_port):
        # Initialize connection to server
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Initialize pygame
        pygame.init()
        self.screen = pygame.display.set_mode((500, 500))  # Set the window size
        self.clock = pygame.time.Clock()  # For controlling the frame rate

        # Connect to the server
        try:
            self.client.connect((server_ip, server_port))
            print("Connected to server")
        except socket.error as e:
            print(f"Error connecting to server: {e}")
            raise Exception("Connection failed")

        # Generate RSA key pair
        self.private_key, self.public_key = self.generate_rsa_key_pair()
        print("Client's RSA key pair generated.")

        # Send public key to server
        self.client.send(self.public_key)
        print("Client's public key sent to server.")

        # Wait and store server's public key
        server_public_key_pem = self.recv_all(self.client)  # Adjust buffer size as needed
        self.server_public_key = serialization.load_pem_public_key(server_public_key_pem)
        print("Server's public key received and loaded.")

    def recv_all(self, sock, buffer_size=4096):
        """Read from sock until a short (or empty) chunk signals end of data."""
        data = b''
        while True:
            part = sock.recv(buffer_size)
            data += part
            if len(part) < buffer_size:
                break
        return data

    def generate_rsa_key_pair(self):
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

    def send_message(self, hotkey):
        """Send one of the canned chat messages bound to z/x/c."""
        try:
            if hotkey == 'z':
                message = "Congratulations!"
            elif hotkey == 'x':
                message = "It works!"
            elif hotkey == 'c':
                message = "Ready?"
            # Encrypt the message using the client's private key
            encrypted_message = self.encrypt_message(message)

            # Send the encrypted message to the server
            self.client.send(message.encode())
        except socket.error as e:
            print(f"Error sending message: {e}")

    def encrypt_message(self, message):
        """Encrypt message with the server's public RSA key."""
        # Ensure the message is a string
        if not isinstance(message, str):
            raise ValueError("Message must be a string")

        # Convert the message to bytes
        message_bytes = message.encode()

        # Encrypt the message using the server's public key
        encrypted_message_bytes = self.server_public_key.encrypt(
            message_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # Convert the encrypted bytes to a string representation
        encrypted_message = "ENCRYPTED:" + encrypted_message_bytes.hex()
        return encrypted_message

    def send_control(self, control_command):
        try:
            self.client.send(control_command.encode())
        except socket.error as e:
            print(f"Error sending control command: {e}")

    def send_heartbeat(self):
        """Poll the server for updated game state on the same interval
        the server's game loop runs on.
        """
        while self.running:
            self.send_control("get")
            time.sleep(0.2)  # Sleep for the duration of the server's update interval

    def start_heartbeat_thread(self):
        self.heartbeat_thread = threading.Thread(target=self.send_heartbeat)
        self.heartbeat_thread.start()

    def receive_game_state(self):
        """Receive game state (or chat messages) from the server and
        update the display as new state comes in.
        """
        while self.running:
            try:
                data = self.client.recv(4096).decode()

                if data:
                    if "user " in data and ": " in data:  # Check if the data is a message
                        print(data)  # Print the message to the console
                    else:
                        snake_positions, snack_positions = self.parse_game_state(data)
                        self.update_display(snake_positions, snack_positions)
            except Exception as e:
                print(f"Error receiving game state: {e}")

    def start_receiving_thread(self):
        self.running = True
        self.receive_thread = threading.Thread(target=self.receive_game_state)
        self.receive_thread.start()

    def parse_game_state(self, game_state):
        """Parse the server's wire format ("<players>|<snacks>") into
        lists of (x, y) tuples.
        """
        # Split the game state into snake and snack parts
        snake_part, snack_part = game_state.split('|')

        # Parse snake positions
        snake_positions = [
            tuple(map(int, pos[1:-1].split(', '))) for pos in snake_part.split('*') if pos
        ]

        # Parse snack positions
        snack_positions = [
            tuple(map(int, pos[1:-1].split(', '))) for pos in snack_part.split('**') if pos
        ]

        return snake_positions, snack_positions

    def draw_grid(self, w, rows, surface):
        """Draw the grid lines for a w x w board split into `rows` cells."""
        size_btwn = w // rows  # Gives us the distance between the lines

        x = 0  # Keeps track of the current x
        y = 0  # Keeps track of the current y
        for _ in range(rows):  # We will draw one vertical and one horizontal line each loop
            x = x + size_btwn
            y = y + size_btwn

            pygame.draw.line(surface, (255, 255, 255), (x, 0), (x, w))
            pygame.draw.line(surface, (255, 255, 255), (0, y), (w, y))

    def update_display(self, snake_positions, snack_positions):
        """Redraw the board: grid, every snake segment, and every snack."""
        # Clear screen
        self.screen.fill((0, 0, 0))
        self.draw_grid(500, 20, self.screen)

        # Constants for drawing
        BLOCK_SIZE = 25  # Size of each block (snake segment/snack)
        SNAKE_COLOR = (255, 0, 0)  # Color for the snake, e.g., red
        SNACK_COLOR = (0, 255, 0)  # Color for the snacks, e.g., green

        # Draw snake
        for pos in snake_positions:
            rect = (pos[0] * BLOCK_SIZE, pos[1] * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
            pygame.draw.rect(self.screen, SNAKE_COLOR, rect)
        # Draw snacks
        for pos in snack_positions:
            rect = (pos[0] * BLOCK_SIZE, pos[1] * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
            pygame.draw.rect(self.screen, SNACK_COLOR, rect)

        # Update display
        pygame.display.update()

    def run(self):
        self.start_receiving_thread()
        self.start_heartbeat_thread()

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    self.send_control("quit")
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        self.send_control("up")
                    elif event.key == pygame.K_DOWN:
                        self.send_control("down")
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                        self.send_control("left")
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        self.send_control("right")
                    elif event.key == pygame.K_r:  # Assuming 'r' for reset
                        self.send_control("reset")
                    elif event.key == pygame.K_z:
                        self.send_message('z')
                    elif event.key == pygame.K_x:
                        self.send_message('x')
                    elif event.key == pygame.K_c:
                        self.send_message('c')
                    elif event.key == pygame.K_q:  # Assuming 'q' for quit
                        self.send_control("quit")
                        running = False

            self.clock.tick(10)

        self.running = False
        self.heartbeat_thread.join()
        self.receive_thread.join()  # Wait for the thread to finish

        # Close the connection when done
        self.client.close()
        pygame.quit()


if __name__ == "__main__":
    SERVER_IP = "localhost"
    SERVER_PORT = 5555
    client = SnakeClient(SERVER_IP, SERVER_PORT)
    client.run()
