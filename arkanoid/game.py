import functools
import importlib
import itertools
import logging
import os
import random

import pygame
from pygame.sprite import Sprite # 🔸 필살기 아이템 생성을 위해 Sprite 임포트

from arkanoid.event import receiver
from arkanoid.rounds.round1 import Round1
from arkanoid.sprites.ball import Ball
from arkanoid.sprites.enemy import Enemy
from arkanoid.sprites.paddle import (ExplodingState,
                                     Paddle,
                                     MaterializeState)
from arkanoid.utils.util import (load_high_score,
                                 load_png,
                                 load_png_sequence,
                                 save_high_score)
from arkanoid.utils import ptext

# 로깅 설정은 유지합니다.
LOG = logging.getLogger(__name__)

# 게임 FPS(초당 프레임 수)
# 게임이 1초에 60번 업데이트되므로 공/패들의 이동 속도도 이 기준에 맞춰 설계됨.
GAME_SPEED = 60

# 메인 게임 창 해상도 (가로 600px, 세로 800px)
DISPLAY_SIZE = 600, 800

# 화면 상단의 HUD(점수, 하이스코어, 타이머)를 위해 비워둘 공간
TOP_OFFSET = 150

# 윈도우 창의 제목
DISPLAY_CAPTION = 'Arkanoid'

# 공이 패들에서 시작할 때의 각도 (라디안)
# (너무 수직이면 게임 진행 어려움 → 최소값 제한 코멘트 있음)
BALL_START_ANGLE_RAD = 5.0   # 286.48도 # -3.14보다 작으면 안 됨

# 공의 '목표 기본 속도'
# 매 프레임 공은 이 속도에 맞춰 움직이려 함 (normalize 로직 때문)
BALL_BASE_SPEED = 8  # pixels per frame

# 공의 최대 속도 (너무 빨라지지 않도록 상한 설정)
BALL_TOP_SPEED = 12  # px/frame

# 매 프레임 공 속도를 BASE 속도로 되돌리는 정도
# (0.02면 매우 서서히 BASE_SPEED로 복귀함)
BALL_SPEED_NORMALISATION_RATE = 0.02

# 벽돌(brick)에 맞을 때 공 속도 증가량
BRICK_SPEED_ADJUST = 0.3    # 0.5 -> 0.3으로 변경

# 벽(edge)에 맞을 때 공 속도 증가량
WALL_SPEED_ADJUST = 0.1      # 0.2에서 0.1로 변경

# 패들의 이동 속도
PADDLE_SPEED = 10

# 파워업/필살기 아이템의 표준 크기 (StartScreen 참고)
ITEM_ICON_SIZE = (44, 28)

# The fonts.
MAIN_FONT = os.path.join(os.path.dirname(__file__), 'data', 'fonts',
                         'generation.ttf')
ALT_FONT = os.path.join(os.path.dirname(__file__), 'data', 'fonts',
                        'optimus.otf')

# Initialise the pygame modules.
pygame.init()


class Arkanoid:
    """Manages the overall program. This will start and end new games."""

    def __init__(self):
        # Initialise the clock.
        self._clock = pygame.time.Clock()

        # Create the main screen (the window) and default background.
        self._screen = self._create_screen()
        self._background = self._create_background()
        self._display_logo()
        self._display_score_titles()
        self._high_score = load_high_score()

        # The start screen displayed before the game is started.
        self._start_screen = StartScreen(self._start_game)

        # Reference to a running game, when one is in play.
        self._game = None

        # Whether we're running.
        self._running = True
        
        ### TIMER 변수 추가해봄 ##-----------------------------------
        self.level_time_limit = 250              # 제한 시간(초)
        self.time_left = self.level_time_limit
        self._last_time_tick = pygame.time.get_ticks()
        
        #지금 어떤 라운드 객체인지 추적용
        self._current_round = None
        #-----------------------------------------------------------
        
        # 시간 초과 상태 플래그 --------------------------
        self.time_over = False          # 시간이 다 되면 True
        self._time_over_drawn = False   # GAME OVER 텍스트 이미 그렸는지 여부
        # -----------------------------------------------
        
        # Set up the top level event handlers.
        def quit_handler(event):
            self._running = False
        receiver.register_handler(pygame.QUIT, quit_handler)

        # Initialise the scores.
        self._display_player_score = functools.partial(self._display_score,
                                                       y=35)
        self._display_high_score = functools.partial(self._display_score,
                                                     y=100)
        # 타이머 숫자 표시용 (y=135에 그림) -----------------------------
        self._display_timer = functools.partial(self._display_score,
                                                y=135)
        #--------------------------------------------------
        
        self._display_player_score(0)
        self._display_high_score(self._high_score)
        # 처음 화면에 60초 찍어두기
        self._display_timer(int(self.time_left))

    def main_loop(self):
        """Starts the main loop of the program which manages the screen
        interactions and game play.

        Pretty much everything takes place within this loop.
        """
        while self._running:
            # Game runs at 60 fps.
            self._clock.tick(GAME_SPEED)

            # Receive and dispatch events.
            receiver.receive()

            if not self._game:
                self._start_screen.show()
            else:
                 # 🔹 [추가] 라운드가 바뀌었는지 체크해서, 바뀌었으면 타이머 리셋
                if self._current_round is not self._game.round:
                    self.time_left = self.level_time_limit
                    self._last_time_tick = pygame.time.get_ticks()
                    self.time_over = False
                    self._time_over_drawn = False
                    self._current_round = self._game.round
                    self._display_timer(int(self.time_left))
                        
                #아직 시간 안 끝났으면 평소처럼 게임 업데이트 -----
                if not self.time_over:
                    self._game.update()
                    self._display_player_score(self._game.score) 
                #--------------------------------------
                
                    # TIMER UPDATE: 게임이 진행 중일 때만 시간 감소 ------------------
                    if not self._game.over and self.time_left > 0:
                        current_tick = pygame.time.get_ticks()
                        dt = (current_tick - self._last_time_tick) / 1000.0  # ms → 초
                        self.time_left -= dt
                        self._last_time_tick = current_tick

                        # 0 이하로 내려가는 거 방지 + 시간 끝나면 게임 오버 처리
                        if self.time_left <= 0:
                            self.time_left = 0
                            self.time_over = True   # 시간 초과 = 게임 종료

                    # 화면에 남은 시간 숫자 그리기
                    self._display_timer(int(self.time_left))
                    # (일반적인) 게임 오버 처리: 라이프 다 쓰거나 클리어했을 때
                    # 이제는 바로 게임을 없애지 말고, GAME OVER 화면 모드로 전환
                    if self._game.over and not self.time_over:
                         # 하이스코어 저장은 한 번만
                        if not self._time_over_drawn:
                            if self._game.score > self._high_score:
                                self._high_score = self._game.score
                                self._display_high_score(self._high_score)
                                save_high_score(self._high_score)
                        self.time_over = True
                #-------------------------------------------------------------
                # 시간이 다 된 상태(time_over == True)면: 화면에 GAME OVER만 띄우고 멈춤
                else:
                    # 타이머 숫자를 0으로 유지해서 계속 보이게
                    self._display_timer(int(self.time_left))

                    # GAME OVER 텍스트를 한 번만 그리자
                    if not self._time_over_drawn:
                        ptext.draw(
                            'GAME OVER',
                            center=(self._screen.get_width() // 2,
                                    DISPLAY_SIZE[1] // 2),
                            fontname=MAIN_FONT,
                            fontsize=48,
                            color=(255, 0, 0),
                            shadow=(1.0, 1.0),
                            scolor="black",
                        )
                        self._time_over_drawn = True
                    
            # Display all updates.
            pygame.display.flip()

        LOG.debug('Exiting')

    def _start_game(self, round_no):
        """Callback invoked by the start screen when a user begins a game,
        either by hitting the spacebar, or by entering a specific round number
        to start at.

        Args:
            round_no:
                The round number the user entered.

        """
        module_name = 'arkanoid.rounds.round{}'.format(round_no)
        try:
            module = importlib.import_module(module_name)
            round_cls = getattr(module, 'Round{}'.format(round_no))
        except (ImportError, AttributeError):
            LOG.exception('Unable to import round')
        else:
            # 타이머 리셋 --------------------
            self.time_left = self.level_time_limit      # 다시 90초
            self._last_time_tick = pygame.time.get_ticks()
            self.time_over = False
            self._time_over_drawn = False
            self._display_timer(int(self.time_left))

            # [수정 시작] Game 클래스에 배경 Surface 전달
            self._game = Game(background=self._background, round_class=round_cls)
            # [수정 끝]
            
            # 현재 라운드 기억 (라운드 바뀔 때 타이머 리셋용)
            self._current_round = self._game.round
            
            self._start_screen.hide()
            # -----------------------------------------
            
    def _create_screen(self):
        pygame.display.set_mode(DISPLAY_SIZE)
        pygame.display.set_caption(DISPLAY_CAPTION)
        pygame.mouse.set_visible(False)
        screen = pygame.display.get_surface()
        return screen

    def _create_background(self):
        background = pygame.Surface(self._screen.get_size())
        background = background.convert()
        background.fill((0, 0, 0))
        return background

    # 💡 [수정] 로고 이미지 크기 조정 코드 추가
    def _display_logo(self):
        image, _ = load_png('logo.png')
        
        # 이미지 크기를 400x145로 조정합니다.
        target_size = (400, 145)
        if image.get_size() != target_size:
             # 성능과 품질을 위해 smoothscale을 사용합니다.
            image = pygame.transform.smoothscale(image.convert_alpha(), target_size)
            
        self._screen.blit(image, (5, 0))

    def _display_score_titles(self):
        ptext.draw('1UP', (self._screen.get_width() - 55, 10), #70,10
                   fontname=MAIN_FONT,
                   fontsize=20,  #24
                   color=(230, 0, 0))
        ptext.draw('HIGH SCORE', (self._screen.get_width() - 165, 65), #-205, 75가 높이 클-낮
                   fontname=MAIN_FONT,
                   fontsize=20,  #24
                   color=(230, 0, 0))
        
        # ptext.draw('timer', (self._screen.get_width() - 91, 135), #-205, 75
        #            fontname=MAIN_FONT,
        #            fontsize=20,  #24
        #            color=(230, 0, 0))

    def _display_score(self, value, y):
        # 점수를 그리는 surface를 하나 만든다. 가로150 세로 20
        # .convert_alpha() : 투명(알파) 채널 있는 Surface로 변환
        score_surf = pygame.Surface((150, 20)).convert_alpha() #150,20
        
        # ptext로 value(점수 숫자)를 score_surf 위에 그린다.
        ptext.draw(str(value),
                   #topright=(150, 0) : score_surf의 오른쪽 위 모서리를 기준으로 배치
                   topright=(150, 0),
                   fontname=MAIN_FONT,
                # 숫자 글씨 크기
                   fontsize=20,
                   color=(255, 255, 255),
                   surf=score_surf)
        # 메인 화면에서의 실제 위치 계산
        # - x : 화면 오른쪽에서 160px 안쪽
        # - y : 함수 인자로 받은 y 그대로 사용
        position = self._screen.get_width() - 160, y-10      #160,y
        # 배경을 한 번 먼저 덮어씌워서 이전 점수를 지운다.
        # self._background의 같은 위치 영역을 복사해서 덮어버리는 느낌.
        self._screen.blit(self._background, position, score_surf.get_rect())
        # 그 위에 방금 그린 score_surf(숫자) 를 올려서 최종 표시.
        self._screen.blit(score_surf, position)


class StartScreen:
    """Used to display the screen shown when the program is first run, and
    before a game is started.

    Apart from displaying some general information about the game, the start
    screen is also responsible for capturing user input to decide when to
    start a game, and which level to start at.
    """

    def __init__(self, on_start):
        """Initialise the start screen.

        Args:
            on_start:
                Callback invoked when a player starts a new game. The callback
                should accept a single argument: the round number that the
                game will start at.
        """
        self._on_start = on_start
        self._screen = pygame.display.get_surface()

        # Whether we've reinitialised the screen.
        self._init = False

        # The key for the powerups - their images with names and descriptions.
        # ITEM_ICON_SIZE (44, 28)에 맞춰 크기가 조정됨
        ICON_W, ICON_H = ITEM_ICON_SIZE # 🔸 표준 아이템 크기 사용
        self._powerups = (
                          (itertools.cycle(load_png_sequence('powerup_life')),
                           'extra life',
                           'gain an additional\nlife'), #gain an additional\nvaus
                          
                          (itertools.cycle(load_png_sequence('powerup_expand')),
                          'expand',
                          'expands the paddle'), 
                          
                          (itertools.cycle(load_png_sequence('powerup_duplicate')),
                           'duplicate',
                           'duplicates the ball'),
                          
                          (itertools.cycle(load_png_sequence('powerup_slow')),  
                           'slow',
                           'slow down the speed'), # 슬로우
                          
                          (itertools.cycle(load_png_sequence('powerup_reduce')),
                           'reduce',
                           'reduces the paddle'), # reduce
                          
                          (itertools.cycle(load_png_sequence('powerup_speedup')),  
                           'speedup',
                           'speed up the ball'))  # speedup

        # Whether the event listeners have been registered.
        self._registered = False

        self._text_colors_1 = itertools.cycle([(255, 255, 255),
                                               (255, 255, 0)])
        self._text_color_1 = None

        self._text_colors_2 = itertools.cycle([(255, 255, 0),
                                               (255, 0, 0)])
        self._text_color_2 = None

        # The text entered by the user.
        self._user_input = ''
        self._user_input_pos = None

        # Keep track of display count for animation purposes.
        self._display_count = 0

    def show(self):
        """Display the start screen and register event listeners for
        capturing keyboard input.

        This method is designed to be called repeatedly by the main game loop.
        """
        if not self._registered:
            receiver.register_handler(pygame.KEYUP, self._on_keyup)
            self._registered = True
        
        if not self._init:
           self._init = True
           self._screen.blit(pygame.Surface((600, 650)), (0, TOP_OFFSET))

        ptext.draw('item', (245, 200),   # 수정함
                   fontname=ALT_FONT,
                   fontsize=32,
                   color=(255, 255, 255))
        
        left, top = 30, 270   # 30, 270   
        ICON_W, ICON_H = ITEM_ICON_SIZE # 🔸 표준 아이템 크기 사용
        
        for anim, name, desc in self._powerups:   
            if self._display_count % 4 == 0:
                image, _ = next(anim)
                
                # 2️⃣ 알파(투명) 보존 + 크기 조정 (수정) ---------
                image = image.convert_alpha()
                if image.get_size() != (ICON_W, ICON_H):
                    image = pygame.transform.smoothscale(image, (ICON_W, ICON_H))
                # ---------------- 
                self._screen.blit(image, (left, top))
                ptext.draw(name.upper(), (left + image.get_width() + 20,
                                          top-3),
                           fontname=ALT_FONT,
                           fontsize=20,
                           color=(255, 255, 255))
                ptext.draw(desc.upper(), (left, top + 25),
                           fontname=ALT_FONT,
                           fontsize=14,
                           color=(255, 255, 255))
            left += 180

            if left > 400:
                left = 30
                top += 100
        
        # 깜빡이는 텍스트 색상 주기
        if self._display_count % 15 == 0:
            self._text_color_1 = next(self._text_colors_1)
            self._text_color_2 = next(self._text_colors_2)

        ptext.draw('SPACEBAR TO START', (50, 500),
                fontname=ALT_FONT,
                fontsize=48,
                color=self._text_color_1,
                shadow=(1.0, 1.0),
                scolor="grey")

        ptext.draw('OR ENTER LEVEL', (160, 575),
                fontname=ALT_FONT,
                fontsize=32,
                color=self._text_color_2)

        self._user_input_pos = ptext.draw(self._user_input, (280, 625),
                                       fontname=ALT_FONT,
                                       fontsize=40,
                                       color=(255, 255, 255))[1]

        ptext.draw('Based on original Arkanoid game\n'
                'by Taito Corporation 1986',
                (100, 700),
                align='center',
                fontname=ALT_FONT,
                fontsize=24,
                color=(128, 128, 128))

        self._display_count += 1

    def hide(self):
        """Hide the start screen and unregister event listeners."""
        receiver.unregister_handler(self._on_keyup)
        self._registered = False
        self._init = False

    def _on_keyup(self, event):
        """Event handler for capturing user input.

        Args:
            event:
                The pygame event.

        """
        numeric_keys = {pygame.K_0: '0', pygame.K_1: '1', pygame.K_2: '2',
                        pygame.K_3: '3', pygame.K_4: '4', pygame.K_5: '5',
                        pygame.K_6: '6', pygame.K_7: '7', pygame.K_8: '8',
                        pygame.K_9: '9'}
        if event.key == pygame.K_SPACE:
            self._on_start(1)
        elif event.key in numeric_keys and len(self._user_input) < 2:
            self._user_input += numeric_keys[event.key]
        elif event.key == pygame.K_BACKSPACE:
            self._user_input = ''
            self._screen.blit(pygame.Surface((50, 50)), self._user_input_pos)
        elif event.key == pygame.K_RETURN and self._user_input:
            self._screen.blit(pygame.Surface((50, 50)), self._user_input_pos)
            self._on_start(int(self._user_input))
            self._user_input = ''


class Game:
    """Represents a running Arkanoid game.

    An instance of a Game comes into being when a player starts a new game.
    """

    # [수정] background 인자를 추가했습니다.
    def __init__(self, background, round_class=Round1, lives=3):
        """Initialise a new Game.

        Args:
            background:
                The main black background surface from the Arkanoid class.
            round_class:
                The class of the round to start, default Round1.
            lives:
                Optional number of lives for the player, default 3.
        """
        # Keep track of the score and lives throughout the game.
        self.lives = lives
        self.score = 0

        # Reference to the main screen.
        self._screen = pygame.display.get_surface()
        # [수정] background 인자를 인스턴스 변수로 저장
        self._background = background

        # The life graphic.
        self._life_img, _ = load_png('paddle_life.png')
        # The life graphic positions.
        self._life_rects = []

        # The current round.
        self.round = round_class(TOP_OFFSET)

        # The sprites in the game.
        self.paddle = Paddle(left_offset=self.round.edges.left.rect.width,
                             right_offset=self.round.edges.right.rect.width,
                             bottom_offset=60,
                             speed=PADDLE_SPEED)

        ball = Ball(start_pos=self.paddle.rect.midtop,
                    start_angle=BALL_START_ANGLE_RAD,
                    base_speed=BALL_BASE_SPEED,
                    top_speed=BALL_TOP_SPEED,
                    normalisation_rate=BALL_SPEED_NORMALISATION_RATE,
                    off_screen_callback=self._off_screen)

        # The game starts with a single ball in play initially.
        self.balls = [ball]

        # The currently applied powerup, if any.
        self.active_powerup = None

        # The current enemies in the game.
        self.enemies = []

        # 🔸 필살기 관련 변수
        self.special_ready = False  # 필살기 사용 가능 상태
        self.special_used = False   # 현재 라운드에서 필살기 사용 여부
        self.special_item = None    # 화면에 존재하는 필살기 아이템 Sprite
        self.special_brick = None   # 💡 [추가] 필살기를 가지고 있는 블록
        try:
            # load_png는 기본적으로 data/graphics 폴더를 가정하므로, 경로가 올바르다면 사용합니다.
            img, _ = load_png("special_item.png")
            
            # ⭐ [수정] 필살기 아이템 이미지를 파워업 아이템과 동일한 크기로 조정
            if img.get_size() != ITEM_ICON_SIZE:
                self.special_item_image = pygame.transform.smoothscale(img.convert_alpha(), ITEM_ICON_SIZE)
            else:
                self.special_item_image = img.convert_alpha()
            
            # 💡 [디버깅 추가] 로드 성공 메시지
            LOG.info("✅ special_item.png 로드 및 크기 조정 성공.")
        except Exception:
            self.special_item_image = pygame.Surface(ITEM_ICON_SIZE)
            self.special_item_image.fill((255, 255, 0))
            # 💡 [디버깅 추가] 로드 실패 메시지
            LOG.error("🚨 special_item.png 파일을 찾을 수 없어 노란색 임시 Surface 사용.")
        self.flash_timer = 10        # 화면 플래시 효과 타이머 (초기값 10 유지)
        
        # Hold a reference to all the sprites for redrawing purposes.
        self.sprites = []

        # Create event handlers required by the game.
        self._create_event_handlers()

        # Whether the game is finished.
        self.over = False

        # The current game state which handles the behaviour for the
        # current stage of the game.
        self.state = GameStartState(self)

    def update(self):
        """Update the state of the running game."""
        
        # 1. Clear the screen.
        # [수정1] 게임 보드 배경을 TOP_OFFSET(150px) 아래부터 그려 HUD 영역을 보존합니다.
        self._screen.blit(self.round.background, (0, TOP_OFFSET))

        # 2. Delegate to the active state.
        self.state.update()
        
        # 3. Update all sprites.
        for sprite in self.sprites:
            sprite.update()
            
        # 🔸 필살기 아이템 낙하 및 획득 처리 
        if self.special_item and self.special_item.visible:
            
            # ⭐ [수정 유지] 첫 프레임 플래그 체크 및 제거 (즉시 획득 방지 로직)
            is_first_frame = getattr(self.special_item, 'first_frame', False)
            if is_first_frame:
                del self.special_item.first_frame
            
            # ➡️ 아이템 낙하 (매 프레임 2픽셀씩 Y좌표 증가)
            # 요구사항: 속도 2로 떨어지게끔 유지
            self.special_item.rect.y += 2 # speed=2를 하드코딩

            # 바닥 도달 시 사라짐 (화면 하단)
            if self.special_item.rect.top > self._screen.get_height():
                # 💡 [수정] 스프라이트 리스트에서 제거 시도 시 오류 방지
                try:
                    self.sprites.remove(self.special_item)
                except ValueError:
                    pass # 이미 리스트에 없다면 무시
                
                self.special_item = None
                LOG.info("필살기 아이템 사라짐.")

            # ➡️ 패들과 충돌 시 필살기 획득
            # 첫 프레임이 아닐 때만 충돌 체크를 수행하여 즉시 획득 버그를 방지
            elif not is_first_frame and self.special_item.rect.colliderect(self.paddle.rect): # ⭐ [수정 유지] 첫 프레임 체크
                self.special_ready = True
                
                # 📢 [추가] 필살기 아이템 획득 시 패들 이미지 변경
                self.paddle.activate_special_image()
                
                # 💡 [수정] 스프라이트 리스트에서 제거 시도 시 오류 방지
                try:
                    self.sprites.remove(self.special_item)
                except ValueError:
                    pass
                    
                self.special_item = None
                LOG.info("필살기 획득! 이제 'S' 키를 눌러 사용 가능.")

        # 4. Draw the sprites.
        for sprite in self.sprites:
            if sprite.visible:
                self._screen.blit(sprite.image, sprite.rect)

        # 🔸 필살기 플래시 효과 그리기 
        if self.flash_timer > 0:
            
            # [수정2] 게임 영역 크기 계산 (화면 너비, 화면 높이 - TOP_OFFSET)
            game_area_width = self._screen.get_width()
            game_area_height = self._screen.get_height() - TOP_OFFSET
            
            # 게임 영역 크기만큼의 흰색 반투명 오버레이를 생성
            overlay = pygame.Surface((game_area_width, game_area_height), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, 128)) # 흰색, 반투명
            
            # 오버레이를 (0, TOP_OFFSET) 위치부터 그립니다. (HUD 영역 제외)
            self._screen.blit(overlay, (0, TOP_OFFSET))
            
            self.flash_timer -= 1


        # 5. Update the lives.
        self._update_lives()

    # 🔸 [삭제] _update_sprites 메서드는 update에 통합되어 삭제됨.

    def _update_lives(self):
        """Update the number of remaining lives displayed on the screen."""
        # Erase the existing lives.
        for rect in self._life_rects:
            # 💡 [수정] Game.__init__에서 받은 self._background를 사용하여 이전 라이프 아이콘을 지웁니다.
            self._screen.blit(self._background, rect, rect)
        self._life_rects.clear()

        # Display the remaining lives.
        left = self.round.edges.left.rect.width
        top = self._screen.get_height() - self._life_img.get_height() - 5

        for life in range(self.lives - 1):
            self._life_rects.append(
                self._screen.blit(self._life_img, (left, top)))
            left += self._life_img.get_width() + 5

    def on_brick_collide(self, brick, sprite):
        """Called by a sprite when it collides with a brick.

        In this case a sprite might be the ball, or a laser beam from the
        laser paddle.

        Args:
            brick:
                The Brick instance the sprite collided with.
            sprite:
                The sprite instance that struck the brick.
        """
        # Increment the collision count.
        brick.collision_count += 1

        # Has the brick been destroyed, based on the collision count?
        if brick.visible:
            # Still visible, so animate to indicate strike.
            brick.animate()
        else:
            # Brick has been destroyed.
            if brick.value:
                # Add this brick's value to the score.
                self.score += brick.value

            # Tell the round that a brick has gone, so that it can decide
            # whether the round is completed.
            self.round.brick_destroyed()
            
            # 💡 [수정] 필살기 아이템 생성 로직: 
            # 1. 파괴된 벽돌이 지정된 special_brick이고
            # 2. 화면에 special_item이 존재하지 않을 때만 생성
            if brick is self.special_brick and self.special_item is None:
                
                # ⭐ 아이템 생성 위치를 벽돌의 하단 중앙 + 1픽셀 아래로 변경하여
                # 블록이 깨진 위치(brick.rect.centerx, brick.rect.bottom)에서 낙하 시작
                self.spawn_special_item((brick.rect.centerx, brick.rect.bottom + 1))
                self.special_brick = None # 💡 [추가] 아이템을 드롭했으니 지정 해제
                LOG.info("✅ 지정된 필살기 블록 파괴! 아이템 생성 완료.")
                
            elif brick is self.special_brick:
                # 💡 [디버깅 추가] 지정된 블록이지만 이미 아이템이 화면에 있는 경우 (예외 상황)
                LOG.error("아이템 생성 실패: 지정된 블록이지만, 화면에 이미 아이템이 존재합니다.")

        if brick.powerup_cls:
            # There is a powerup in the brick.
            # Figure out whether we should release it.
            release = not brick.visible  # Always release on brick destruction

            if not release:
                # Brick hasn't been destroyed, so randomly decide whether
                # to release or not.
                release = random.choice((True, False))

            if release:
                powerup = brick.powerup_cls(self, brick)
                brick.powerup_cls = None

                # Display the powerup.
                self.sprites.append(powerup)

        if not self.enemies and self.round.can_release_enemies():
            # Setup the enemy sprites.
            self._setup_enemies()

            # Release them into the game.
            # Note that once an enemy is destroyed, it will call
            # Game.release_enemy() itself to respawn itself.
            for enemy in self.enemies:
                self.release_enemy(enemy)

    def on_enemy_collide(self, enemy, sprite):
        """Called by a sprite when it collides with an enemy.

        In this case a sprite might be the ball, or a laser beam from the
        laser paddle.

        Args:
            enemy:
                The Enemy instance the sprite collided with.
            sprite:
                The sprite instance that struck the enemy.
        """
        enemy.explode()
        self.score += 500
        # Temporarily remove the enemy sprites from the balls to prevent
        # the balls from colliding with the explosion. The enemy sprites
        # are re-added to the balls when they are re-released.
        for ball in self.balls:
            ball.remove_collidable_sprite(enemy)

    def _setup_enemies(self):
        """Set up the enemy sprites ready for release into the game."""
        collidable_sprites = []
        collidable_sprites += self.round.edges
        collidable_sprites += self.round.bricks

        for _ in range(self.round.num_enemies):
            # Create the sprite.
            enemy_sprite = Enemy(self.round.enemy_type,
                                 self.paddle,
                                 self.on_enemy_collide,
                                 collidable_sprites,
                                 on_destroyed=self.release_enemy)

            # Keep track of the enemy sprites currently in the game.
            self.enemies.append(enemy_sprite)

            # Allow the sprite to be displayed.
            self.sprites.append(enemy_sprite)

    def release_enemy(self, enemy):
        """Release an enemy through one of the top doors.

        Note that this method runs asynchronously and the enemy is not
        necessarily released immediately, but after a short random delay.
        The door from which the enemy is released is selected at random.
        
        Args:
            enemy:
                The enemy sprite to release through one of the doors.
        """
        # Conceal the enemy until the door opens.
        enemy.freeze = True
        enemy.visible = False

        # Callback called when the door is opened.
        def door_open(coords):
            enemy.reset()  # Show the enemy and re-init its movement.
            enemy.rect.topleft = coords
            # Tell the ball(s) about it.
            for ball in self.balls:
                ball.add_collidable_sprite(enemy,
                                           on_collide=self.on_enemy_collide)

        # Trigger opening the door.
        self.round.edges.top.open_door(door_open)

    def _off_screen(self, ball):
        """Callback called by a ball when it goes offscreen.

        Args:
            ball:
                The ball that left the screen.
        """
        if len(self.balls) > 1:
            # There are multiple balls in play, so just take this ball
            # out of play.
            self.balls.remove(ball)
            self.sprites.remove(ball)
            ball.visible = False
        else:
            # This ball is the last in play, so transition to the
            # BallOffScreenState which handles end of life.
            if not isinstance(self.state, BallOffScreenState):
                self.state = BallOffScreenState(self)
                
    # 🔸 필살기 아이템 스폰 메서드 
    def spawn_special_item(self, position):
        """필살기 아이템을 생성하여 화면에 표시합니다.
        
        position은 (x_center, y_bottom_of_brick + 1) 형태를 받습니다.
        """
        if self.special_item is not None:
            # 이미 아이템이 있으면 생성하지 않음
            return

        item = Sprite()
        item.image = self.special_item_image
        # 아이템의 상단 중앙(midtop)을 전달받은 위치에 설정
        # 요구사항: 블록이 깨지면 거기서 나오도록 position을 사용
        item.rect = item.image.get_rect(midtop=position)
        # item.speed = 2 # 속도는 update에서 하드코딩
        item.visible = True
        item.first_frame = True # ⭐ [추가 유지] 생성된 첫 프레임임을 표시 (즉시 획득 방지)
        self.special_item = item
        self.sprites.append(item)
        LOG.info("필살기 아이템 등장!")

    # 🔸 필살기 발동 메서드 
    def activate_special(self):
        """필살기를 발동하고 적들을 폭발시킵니다."""
        # 획득 상태이고, 아직 사용하지 않았다면 발동
        if not self.special_ready or self.special_used:
            return

        LOG.info("필살기 발동! 모든 적 폭파!")

        # 필살기 사용 상태로 변경
        self.special_used = True
        self.special_ready = False # 👈 사용했으므로 준비 상태 해제
        self.flash_timer = 10 # 화면 플래시 효과를 위한 타이머

        # 📢 [추가] 필살기 사용 시 패들 이미지 원래대로 복구
        self.paddle.deactivate_special_image()
        
        # 현재 화면에 보이는 모든 적을 폭파
        for enemy in self.enemies:
            if enemy.visible:
                enemy.explode()
                self.score += 500 # 점수 추가

        # 공이 적과 충돌하지 않도록 임시로 충돌 목록에서 제거
        for enemy in self.enemies:
            for ball in self.balls:
                ball.remove_collidable_sprite(enemy)

        # 문 닫기 취소 (만약 열려 있다면)
        self.round.edges.top.cancel_open_door()


    def _create_event_handlers(self):
        """Create the event handlers for paddle movement."""
        keys_down = 0

        def move_left(event):
            nonlocal keys_down
            if event.key == pygame.K_LEFT:
                self.paddle.move_left()
                keys_down += 1
        self.handler_move_left = move_left

        def move_right(event):
            nonlocal keys_down
            if event.key == pygame.K_RIGHT:
                self.paddle.move_right()
                keys_down += 1
        self.handler_move_right = move_right

        def stop(event):
            nonlocal keys_down
            if event.key == pygame.K_LEFT or event.key == pygame.K_RIGHT:
                if keys_down > 0:
                    keys_down -= 1
                if keys_down == 0:
                    self.paddle.stop()
        self.handler_stop = stop
        
        # 🔸 필살기 발동 핸들러 추가
        def special_activate(event):
            """'S' 키로 필살기 발동을 시도합니다."""
            if event.key == pygame.K_s:
                if self.special_ready and not self.special_used:
                    self.activate_special()
        self.handler_special_activate = special_activate


    @property
    def ball(self):
        """A convenience attribute for accessing the primary ball in the game.

        This is really just an convenient alias so client code doesn't have to
        do game.balls[0] everywhere.

        Returns:
            The priamry ball in the game, or None if no balls currently in
            play.
        """
        try:
            return self.balls[0]
        except IndexError:
            return None

    def __repr__(self):
        class_name = type(self).__name__
        return '{}(round_class={}, lives={})'.format(
            class_name,
            type(self.round).__name__,
            self.lives)


class BaseState:
    """Abstract base class holding behaviour common to all states."""

    def __init__(self, game):
        self.game = game

        LOG.debug('Entered {}'.format(type(self).__name__))

    def update(self):
        """Update the state.

        Sub-states must implement this to perform their state specific
        behaviour. This method is called repeatedly by the main game loop.
        """
        raise NotImplementedError('Subclasses must implement update()')

    def __repr__(self):
        class_name = type(self).__name__
        return '{}({!r})'.format(class_name, self.game)


class GameStartState(BaseState):
    """This state handles the behaviour after the user has begun a new game,
    but before they actually start playing it, e.g. showing an animation
    sequence.
    """

    def __init__(self, game):
        super().__init__(game)

        # The ball and paddle are kept invisible at the very start.
        self.game.paddle.visible = False
        self.game.ball.visible = False

        # Register the event handlers for paddle control.
        receiver.register_handler(pygame.KEYDOWN,
                                  self.game.handler_move_left,
                                  self.game.handler_move_right,
                                  self.game.handler_special_activate) # 💡 필살기 핸들러 추가
        receiver.register_handler(pygame.KEYUP, self.game.handler_stop)

    def update(self):
        # TODO: implement the game intro sequence (animation).
        self.game.state = RoundStartState(self.game)


class RoundStartState(BaseState):
    """This state handles the behaviour that happens at the very beginning of
    a round and just before the real gameplay begins.

    This state initialises the sprites so they are set up ready for a new
    round to begin.
    """

    def __init__(self, game):
        super().__init__(game)

        # Set up the sprites for the round.
        self._setup_sprites()

        # Set up the ball and paddle.
        self._configure_ball()
        self._configure_paddle()
        
        # 🔸 필살기 관련 상태 초기화 
        self.game.special_used = False
        
        # 💡 [추가] 라운드 시작 시 필살기 블록 지정
        if self.game.round.bricks:
            # 현재 라운드의 모든 벽돌 중 하나를 랜덤하게 선택하여 지정
            # self.game.special_brick = random.choice(self.game.round.bricks) # ❌ 이전 코드 (TypeError 발생)
            # 💡 [수정] Group 객체를 리스트로 변환하여 random.choice 사용
            self.game.special_brick = random.choice(self.game.round.bricks.sprites())
            LOG.info(f"Special Brick assigned: {self.game.special_brick}")
        else:
            self.game.special_brick = None
            
        if self.game.special_item:
            if self.game.special_item in self.game.sprites:
                self.game.sprites.remove(self.game.special_item)
            self.game.special_item = None

        # Initialise the sprites' display state.
        self._screen = pygame.display.get_surface()
        self.game.ball.reset()
        self.game.paddle.visible = False
        self.game.ball.visible = False
        # Anchor the ball whilst it's invisible.
        self.game.ball.anchor((self._screen.get_width() / 2,
                               self._screen.get_height() - 100))

        # Whether we've reset the paddle
        self._paddle_reset = False

        # Keep track of the number of update cycles.
        self._update_count = 0

    def _setup_sprites(self):
        """Make all the sprites available for rendering."""
        self.game.sprites.clear()
        self.game.sprites.append(self.game.paddle)
        self.game.sprites.append(self.game.ball)
        self.game.sprites += self.game.round.edges
        self.game.sprites += self.game.round.bricks

    def _configure_ball(self):
        self.game.ball.remove_all_collidable_sprites()

        for edge in self.game.round.edges:
            # Every collision with a wall momentarily increases the speed
            # of the ball.
            self.game.ball.add_collidable_sprite(
                edge,
                speed_adjust=WALL_SPEED_ADJUST)

        self.game.ball.add_collidable_sprite(
            self.game.paddle,
            bounce_strategy=self.game.paddle.bounce_strategy,
            on_collide=self.game.paddle.on_ball_collide)

        for brick in self.game.round.bricks:
            # Make the ball aware of the bricks it might collide with.
            # Every brick collision momentarily increases the speed of
            # the ball.
            self.game.ball.add_collidable_sprite(
                brick,
                speed_adjust=BRICK_SPEED_ADJUST,
                on_collide=self.game.on_brick_collide)

        # Make any round-specific adjustments to the ball.
        self.game.ball.base_speed += self.game.round.ball_base_speed_adjust
        self.game.ball.normalisation_rate += \
            self.game.round.ball_speed_normalisation_rate_adjust

    def _configure_paddle(self):
        # Make any round-specific adjustments to the paddle.
        self.game.paddle.speed += self.game.round.paddle_speed_adjust

    def update(self):
        """Handle the sequence of events that happen at the beginning of a
        round just before gameplay starts.
        """
        caption, ready = None, None

        if self._update_count > 100:
            # Display the caption after a short delay.
            caption = ptext.draw(self.game.round.name,
                                 (235, self.game.paddle.rect.center[1] - 150),
                                 fontname=MAIN_FONT,
                                 fontsize=24,
                                 color=(255, 255, 255))
        if self._update_count > 200:
            # Display the "Ready" message.
            ready = ptext.draw('ready',
                               (250, caption[1][1] + 50),
                               fontname=MAIN_FONT,
                               fontsize=24,
                               color=(255, 255, 255))
            # Anchor the ball to the paddle.
            self.game.ball.anchor(self.game.paddle,
                                  (self.game.paddle.rect.width // 2,
                                   -self.game.ball.rect.height))
            # Display the sprites.
            if not self._paddle_reset:
                self.game.paddle.reset()
                self._paddle_reset = True
            self.game.paddle.visible = True
            self.game.ball.visible = True
        if self._update_count == 201:
            # Animate the paddle materializing onto the screen.
            self.game.paddle.transition(MaterializeState(self.game.paddle))
            # Animate the bricks
            for brick in self.game.round.bricks:
                brick.animate()
        if self._update_count > 310:
            # Erase the text.
            self._screen.blit(self.game.round.background, caption[1])
            self._screen.blit(self.game.round.background, ready[1])
        if self._update_count > 340:
            # Release the anchor.
            self.game.ball.release(BALL_START_ANGLE_RAD)
            # Normal gameplay begins.
            self.game.state = RoundPlayState(self.game)

        self._update_count += 1

        # Don't let the paddle move when it's not displayed.
        if not self.game.paddle.visible:
            self.game.paddle.stop()


class RoundPlayState(BaseState):
    """This state is active when the game is running and the user is
    controlling the paddle and ball.
    """

    def __init__(self, game):
        super().__init__(game)

    def update(self):
        if self.game.round.complete:
            self.game.state = RoundEndState(self.game)


class BallOffScreenState(BaseState):
    """This state handles what happens when gameplay stops due to the
    ball going offscreen.
    """

    def __init__(self, game):
        super().__init__(game)

        # Deactivate the active powerup if set.
        if self.game.active_powerup:
            self.game.active_powerup.deactivate()
            self.game.active_powerup = None

        # 🔸 필살기 아이템 제거 및 상태 초기화
        if self.game.special_item:
            # 💡 [수정] 스프라이트 리스트에서 제거 시도 시 오류 방지
            try:
                self.game.sprites.remove(self.game.special_item)
            except ValueError:
                pass
                
            self.game.special_item = None
        self.game.special_ready = False
        self.game.special_used = False
        
        # 📢 [추가] 라이프 상실(다음 라운드 재시작) 시 패들 이미지 원래대로 복구
        self.game.paddle.deactivate_special_image()

        # Tell the paddle to explode.
        self.game.paddle.transition(
            ExplodingState(self.game.paddle, self._exploded))
        self._explode_complete = False

    def update(self):
        # Wait for the explosion animation to complete.
        if self._explode_complete:
            if self.game.lives - 1 > 0:
                self.game.state = RoundRestartState(self.game)
            else:
                self.game.state = GameEndState(self.game)

    def _exploded(self):
        self._explode_complete = True


class RoundRestartState(RoundStartState):
    """Specialisation of RoundStartState that handles the behaviour when a
    round is restarted due to the ball going off screen.
    """

    def __init__(self, game):
        super().__init__(game)

        # The new number of lives since restarting.
        self._lives = game.lives - 1

        # Conceal any enemy sprites.
        for enemy in self.game.enemies:
            enemy.freeze = True
            enemy.visible = False

        # Cancel any existing open door requests.
        self.game.round.edges.top.cancel_open_door()

        # Whether the enemies have been re-released for this round restart.
        self._enemies_rereleased = False

    def _setup_sprites(self):
        # No need to setup the sprites again on round restart.
        pass

    def _configure_ball(self):
        # No need to configure the ball again on round restart.
        pass

    def _configure_paddle(self):
        # No need to configure the paddle again on round restart.
        pass

    def update(self):
        # Run the logic in the RoundStartState first.
        super().update()

        if self._update_count > 100:
            # Update the number of lives when we display the caption.
            self.game.lives = self._lives
        if self._update_count > 340:
            # Re-release any enemies that were previously active.
            if not self._enemies_rereleased:
                for enemy in self.game.enemies:
                    self.game.release_enemy(enemy)
                self._enemies_rereleased = True


class RoundEndState(BaseState):
    """This state handles the behaviour when the round ends (is completed
    successfully).
    """
    def __init__(self, game):
        super().__init__(game)

        # Deactivate any active powerup.
        if self.game.active_powerup:
            self.game.active_powerup.deactivate()
            self.game.active_powerup = None

        # 🔸 필살기 아이템 제거 및 상태 초기화
        if self.game.special_item:
            # 💡 [수정] 스프라이트 리스트에서 제거 시도 시 오류 방지
            try:
                self.game.sprites.remove(self.game.special_item)
            except ValueError:
                pass
                
            self.game.special_item = None
        self.game.special_ready = False
        self.game.special_used = False
        self.game.special_brick = None # 💡 [추가] 라운드 종료 시 지정 블록 해제

        # 📢 [추가] 라운드 종료 시 패들 이미지 원래대로 복구
        self.game.paddle.deactivate_special_image()

        self._update_count = 0

    def update(self):
        for ball in self.game.balls:
            ball.speed = 0
            ball.visible = False

        self.game.paddle.visible = False

        for enemy in self.game.enemies:
            enemy.visible = False
        self.game.enemies.clear()
        self.game.round.edges.top.cancel_open_door()

        # Pause for a short period after stopping the ball(s).
        if self._update_count > 120:
            # Move on to the next round, carrying over a single ball.
            self.game.balls = self.game.balls[:1]
            if self.game.round.next_round is not None:
                self.game.round = self.game.round.next_round(TOP_OFFSET)
                self.game.state = RoundStartState(self.game)
            else:
                # TODO: special behaviour when user completes whole game.
                self.game.state = GameEndState(self.game)

        self._update_count += 1


class GameEndState(BaseState):
    """This state handles the behaviour when the game ends, either due to all
    lives being lost, or when the player successfully reaches the very end.
    """

    def __init__(self, game):
        super().__init__(game)

        # Bring the ball back onto the screen, but hide it.
        # This prevents the offscreen callback from being called again.
        game.ball.anchor(game.paddle.rect.midtop)
        game.ball.visible = False

        # Indicate that the game is over.
        game.over = True

        # Unregister the event handlers.
        receiver.unregister_handler(self.game.handler_move_left,
                                    self.game.handler_move_right,
                                    self.game.handler_stop,
                                    self.game.handler_special_activate) # 💡 필살기 핸들러 제거

    def update(self):
        pass