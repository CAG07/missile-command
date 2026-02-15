import os
import pygame
#from pygame.locals import *
import random
#import math
import time

from config import *
from functions import *
from city import City
from missile import Missile
from explosion import Explosion
from defense import Defense
from mcgame import McGame
from text import InputBox


# Initialize game engine, screen and clock
pygame.init()

# Try several SDL audio drivers so the mixer works inside
# virtual-environments where the default driver may be absent.
_mixer_ok = False
_orig_audio_driver = os.environ.get("SDL_AUDIODRIVER")
for _driver in [None, "pulseaudio", "alsa", "dsp", "dummy"]:
    try:
        if _driver is not None:
            os.environ["SDL_AUDIODRIVER"] = _driver
        pygame.mixer.init()
        _mixer_ok = True
        break
    except Exception:
        continue
if not _mixer_ok:
    if _orig_audio_driver is not None:
        os.environ["SDL_AUDIODRIVER"] = _orig_audio_driver
    elif "SDL_AUDIODRIVER" in os.environ:
        del os.environ["SDL_AUDIODRIVER"]
screen = pygame.display.set_mode(SCREENSIZE)
pygame.mouse.set_visible(SHOW_MOUSE)
pygame.display.set_caption(TITLE)
clock = pygame.time.Clock()


def main():
    global current_game_state

    # load high-score file
    high_scores = load_scores("scores.json")
    
    # set the random seed - produces more random trajectories
    random.seed()

    #  list of all active explosions
    explosion_list = []
    # list of all active missiles
    missile_list = []
    # TBC - generate the cities
    # need to be replaced with working cities
    city_list = []
    for i in range(1, 8):   # 8 == Max num cities plus defense plus one
        if i == 8 // 2:     # find centre point for gun
            pass
        else:
            city_list.append(City(i, 7))   # 7 == max num cities plus guns
    # Intercepter gun
    defense = Defense()

    # set the game running
    current_game_state = GAME_STATE_RUNNING

    show_high_scores(screen, high_scores)

    # setup the MCGAME AI
    mcgame = McGame(1, high_scores["1"]["score"])

    while True:
        # write event handlers here
        for event in pygame.event.get():
            if event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    # left mouse button -> left silo
                    defense.shoot(missile_list, silo_index=0)
                if event.button == 2:
                    # middle mouse button -> center silo
                    defense.shoot(missile_list, silo_index=1)
                if event.button == 3:
                    # right mouse button -> right silo
                    defense.shoot(missile_list, silo_index=2)
            if event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    exit_game(screen)
                if event.key == K_LCTRL:
                    # Left Ctrl -> left silo
                    defense.shoot(missile_list, silo_index=0)
                if event.key == K_LALT:
                    # Left Alt -> center silo
                    defense.shoot(missile_list, silo_index=1)
                if event.key == K_SPACE:
                    # Space -> right silo
                    defense.shoot(missile_list, silo_index=2)
                if event.key == K_p:
                    pause_game(screen)
            if event.type == KEYUP:
                pass

        # clear the screen before drawing
        screen.fill(BACKGROUND)

        # Game logic and draws
        
        # --- cities
        for city in city_list:
            city.draw(screen)
        
        # --- interceptor turret
        defense.update()
        defense.draw(screen)
        
        # --- missiles
        for missile in missile_list[:]:
            missile.update(explosion_list)
            missile.draw(screen)
            if missile.detonated:
                missile_list.remove(missile)
        
        # --- explosions
        for explosion in explosion_list[:]:
            explosion.update()
            explosion.draw(screen)
            if explosion.complete:
                explosion_list.remove(explosion)

        # --- Draw the interface 
        mcgame.draw(screen, defense)

        # --- update game mcgame
        if current_game_state == GAME_STATE_RUNNING:
            current_game_state = mcgame.update(missile_list, explosion_list, city_list)

        # load message for Game Over and proceed to high-score / menu
        if current_game_state == GAME_STATE_OVER:
            mcgame.game_over(screen)

        # load a message and set new game values for start new level
        if current_game_state == GAME_STATE_NEW_LEVEL:
            mcgame.new_level(screen, defense)
        
        # Update the display
        pygame.display.update()

        # hold for few seconds before starting new level
        if current_game_state == GAME_STATE_NEW_LEVEL:
            time.sleep(3)
            current_game_state = GAME_STATE_RUNNING
        
        # hold for few seconds before proceeding to high-score or back to menu or game over splash
        if current_game_state == GAME_STATE_OVER:
            # Show game over message briefly
            pygame.display.update()
            time.sleep(2)

            # Check if the player qualifies for a high score entry
            score_pos = check_high_score(mcgame.get_player_score(), high_scores)
            if score_pos > 0:
                # Player qualifies — prompt for initials
                input_box = InputBox(100, 100, 140, 32)
                prompt_msg = game_font.render('ENTER YOUR INITIALS:', False,
                                              INTERFACE_SEC)
                prompt_pos = (SCREENSIZE[0] // 2 - (prompt_msg.get_width() // 2),
                              60)
                while not input_box.check_finished():
                    for event in pygame.event.get():
                        input_box.handle_event(event)
                    input_box.update()
                    # Draw prompt and input box (InputBox.draw clears screen)
                    input_box.draw(screen)
                    screen.blit(prompt_msg, prompt_pos)
                    pygame.display.update()

                # Update and save high scores with the entered name
                name = input_box.text if input_box.text.strip() else "---"
                high_scores = update_high_scores(
                    mcgame.get_player_score(), name, high_scores)
                save_high_scores("scores.json", high_scores)

            # Clear the screen before transitioning
            screen.fill(BACKGROUND)
            pygame.display.update()
                
            current_game_state = GAME_STATE_MENU
        
        # display the high scores
        if current_game_state == GAME_STATE_MENU:
            show_high_scores(screen, high_scores)
            current_game_state = 0

        # run at pre-set fps
        clock.tick(FPS)


if __name__ == '__main__':
    main()
