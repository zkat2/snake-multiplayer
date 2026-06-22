"""Core game logic for multiplayer Snake.

Defines the grid-based building blocks (Cube, Snake) and the SnakeGame
class that tracks every player and snack on a shared grid. This module
has no networking code in it; it's used as-is by both snake_server.py
and the legacy single-player prototype.
"""

import random

import pygame


class Cube:
    """A single grid cell. A Snake is a list of these; a snack is one too."""

    rows = 20
    w = 500

    def __init__(self, start, dirnx=1, dirny=0, color=(255, 0, 0)):
        self.pos = start
        self.dirnx = dirnx
        self.dirny = dirny  # "L", "R", "U", "D"
        self.color = color

    def move(self, dirnx, dirny):
        """Move one grid step in the given direction."""
        self.dirnx = dirnx
        self.dirny = dirny
        self.pos = (self.pos[0] + self.dirnx, self.pos[1] + self.dirny)

    def draw(self, surface, eyes=False):
        """Draw this cube on a pygame surface, optionally with eyes (head)."""
        dis = self.w // self.rows
        i = self.pos[0]
        j = self.pos[1]

        pygame.draw.rect(surface, self.color, (i * dis + 1, j * dis + 1, dis - 2, dis - 2))
        if eyes:
            centre = dis // 2
            radius = 3
            circle_middle = (i * dis + centre - radius, j * dis + 8)
            circle_middle2 = (i * dis + dis - radius * 2, j * dis + 8)
            pygame.draw.circle(surface, (0, 0, 0), circle_middle, radius)
            pygame.draw.circle(surface, (0, 0, 0), circle_middle2, radius)


class Snake:
    """A player's snake: a head Cube plus a body of trailing Cubes."""

    def __init__(self, color, pos):
        # pos is given as coordinates on the grid, e.g. (1, 5)
        self.color = color
        self.head = Cube(pos)
        self.body = [self.head]
        self.turns = {}
        self.dirnx = 0
        self.dirny = 1

    def move(self, key):
        """Update direction from a key ('left'/'right'/'up'/'down') and
        advance every Cube in the body, applying queued turns at the
        positions where the head previously changed direction.
        """
        if isinstance(key, str):
            if key == 'left':
                self.dirnx = -1
                self.dirny = 0
                self.turns[self.head.pos[:]] = [self.dirnx, self.dirny]
            elif key == 'right':
                self.dirnx = 1
                self.dirny = 0
                self.turns[self.head.pos[:]] = [self.dirnx, self.dirny]
            elif key == 'up':
                self.dirnx = 0
                self.dirny = -1
                self.turns[self.head.pos[:]] = [self.dirnx, self.dirny]
            elif key == 'down':
                self.dirnx = 0
                self.dirny = 1
                self.turns[self.head.pos[:]] = [self.dirnx, self.dirny]
        else:
            # continue in same direction
            pass

        for i, c in enumerate(self.body):
            p = c.pos[:]
            if p in self.turns:
                turn = self.turns[p]
                c.move(turn[0], turn[1])
                if i == len(self.body) - 1:
                    self.turns.pop(p)
            else:
                c.move(c.dirnx, c.dirny)

    def reset(self, pos):
        """Reset this snake to a single Cube at pos (e.g. after a collision)."""
        self.head = Cube(pos)
        self.body = []
        self.body.append(self.head)
        self.turns = {}
        self.dirnx = 0
        self.dirny = 1

    def add_cube(self):
        """Grow the snake by one Cube, appended behind the current tail."""
        tail = self.body[-1]
        dx, dy = tail.dirnx, tail.dirny

        if dx == 1 and dy == 0:
            self.body.append(Cube((tail.pos[0] - 1, tail.pos[1])))
        elif dx == -1 and dy == 0:
            self.body.append(Cube((tail.pos[0] + 1, tail.pos[1])))
        elif dx == 0 and dy == 1:
            self.body.append(Cube((tail.pos[0], tail.pos[1] - 1)))
        elif dx == 0 and dy == -1:
            self.body.append(Cube((tail.pos[0], tail.pos[1] + 1)))

        self.body[-1].dirnx = dx
        self.body[-1].dirny = dy

    def draw(self, surface):
        """Draw every Cube in the body; the head gets eyes."""
        for i, c in enumerate(self.body):
            if i == 0:
                c.draw(surface, True)
            else:
                c.draw(surface)

    def get_pos(self):
        """Serialize this snake's body positions as a '*'-joined string."""
        positions = [p.pos for p in self.body]
        pos_str = "*".join([str(p) for p in positions])
        return pos_str


class SnakeGame:
    """Tracks every connected player's Snake and the snacks on the grid.

    This is the single source of truth for game state; the server calls
    into it on each tick and broadcasts the result via get_state().
    """

    def __init__(self, rows):
        self.rows = rows
        self.players = {}
        self.snacks = [Cube(random_snack(rows)) for _ in range(5)]

    def add_player(self, user_id, color):
        self.players[user_id] = Snake(color, (10, 10))

    def remove_player(self, user_id):
        self.players.pop(user_id)

    def move(self, moves):
        """Apply this tick's queued moves, then check every player for
        collisions (with themselves, a wall, or nothing - snacks are
        handled in check_collision) and reset anyone who crashed.
        """
        moves_ids = set([m[0] for m in moves])
        still_ids = set(self.players.keys()) - moves_ids
        for move in moves:
            self.move_player(move[0], move[1])
            print("moving player {} to {}".format(move[0], move[1]))

        for still_id in still_ids:
            self.move_player(still_id, None)
            print("moving player {} in the same direction".format(still_id))

        for p_id in self.players.keys():
            if self.check_collision(p_id):
                self.reset_player(p_id)

    def move_player(self, user_id, key=None):
        self.players[user_id].move(key)

    def reset_player(self, user_id):
        x_start = random.randrange(1, self.rows - 1)
        y_start = random.randrange(1, self.rows - 1)
        self.players[user_id].reset((x_start, y_start))

    def get_player(self, user_id):
        return self.players[user_id].head.pos

    def check_collision(self, user_id):
        """Handle snack pickup/growth for user_id and report whether they
        collided with their own body or a wall.
        """
        for snack in self.snacks:
            if self.players[user_id].head.pos == snack.pos:
                self.snacks.remove(snack)
                self.snacks.append(Cube(random_snack(self.rows)))
                self.players[user_id].add_cube()

        body_positions = list(map(lambda z: z.pos, self.players[user_id].body[1:]))
        if self.players[user_id].head.pos in body_positions:
            return True

        head_x, head_y = self.players[user_id].head.pos
        if head_x < 0 or head_y < 0 or head_x > self.rows - 1 or head_y > self.rows - 1:
            return True

        return False

    def get_state(self):
        """Serialize all player and snack positions into the wire format
        the clients expect: "<players>|<snacks>", '**'-joined.
        """
        players_pos = [p.get_pos() for p in self.players.values()]
        players_pos_str = "**".join(players_pos)
        snacks_pos = "**".join([str(s.pos) for s in self.snacks])
        return players_pos_str + "|" + snacks_pos


def random_snack(rows):
    """Pick a random (x, y) grid position for a new snack."""
    x = random.randrange(1, rows - 1)
    y = random.randrange(1, rows - 1)
    return (x, y)


if __name__ == "__main__":
    pass
