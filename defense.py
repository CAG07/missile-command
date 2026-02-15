import pygame
import math
from config import *
from missile import Missile


class DefenseSilo():
    """A single defense silo with position, ammo, and gun barrel tracking."""
    def __init__(self, pos, ammo=10):
        self.pos = pos
        self.target_pos = pygame.mouse.get_pos()
        self.gun_end = self.pos
        self.gun_size = 18
        self.color = DEFENSE
        self.x = self.target_pos[0] - self.pos[0]
        self.y = self.target_pos[1] - self.pos[1]
        self.m = 0
        self.angle = math.atan(self.m)
        self.destroyed = False
        self.ammo = ammo

    def draw(self, screen):
        # draw the base
        pygame.draw.circle(screen, self.color, self.pos, 8)
        # draw the launcher
        pygame.draw.line(screen, self.color, self.pos, self.gun_end, 3)

    def update(self):
        self.target_pos = pygame.mouse.get_pos()
        self.x = self.target_pos[0] - self.pos[0]
        self.y = self.target_pos[1] - self.pos[1]
        if self.y != 0:
            self.m = self.x / self.y
        self.angle = math.atan(self.m) + math.pi
        self.gun_end = (self.pos[0] + int(self.gun_size * math.sin(self.angle)),
                        self.pos[1] + int(self.gun_size * math.cos(self.angle)))

    def shoot(self, missile_list):
        if self.ammo > 0:
            missile_list.append(Missile(self.pos, self.target_pos, False, 8, 0, INTERCEPTER_TRAIL, INTERCEPTER))
            self.ammo -= 1
            return True
        return False


class Defense():
    """Manages 3 defense silos: left, center, right."""
    def __init__(self):
        ground_y = SCREENSIZE[1] - GROUND_LEVEL
        # 3 silos evenly spaced: left, center, right
        self.silos = [
            DefenseSilo((SCREENSIZE[0] // 6, ground_y), ammo=10),       # left
            DefenseSilo((SCREENSIZE[0] // 2, ground_y), ammo=10),       # center
            DefenseSilo((SCREENSIZE[0] * 5 // 6, ground_y), ammo=10),   # right
        ]

    def draw(self, screen):
        for silo in self.silos:
            silo.draw(screen)

    def update(self):
        for silo in self.silos:
            silo.update()

    def shoot(self, missile_list, silo_index=None):
        """Fire from a specific silo (0=left, 1=center, 2=right).

        If silo_index is None, fires from the nearest silo with ammo.
        """
        if silo_index is not None:
            if 0 <= silo_index < len(self.silos):
                return self.silos[silo_index].shoot(missile_list)
            return False
        # Fallback: fire from center, then left, then right
        for idx in [1, 0, 2]:
            if self.silos[idx].ammo > 0:
                return self.silos[idx].shoot(missile_list)
        return False

    def get_ammo(self):
        return sum(s.ammo for s in self.silos)

    def set_ammo(self, ammo):
        per_silo = ammo // len(self.silos)
        remainder = ammo % len(self.silos)
        for i, silo in enumerate(self.silos):
            silo.ammo = per_silo + (1 if i < remainder else 0)