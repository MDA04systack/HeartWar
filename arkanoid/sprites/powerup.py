import itertools
import logging
import math

import pygame

from arkanoid.event import receiver
from arkanoid.sprites.paddle import (LaserState,
                                     NormalState,
                                     NarrowState,
                                     WideState)
from arkanoid.utils.util import load_png_sequence

LOG = logging.getLogger(__name__)

# 아이템이 벽돌에서 떨어질 때의 기본 낙하 속도
# The speed the powerup falls from a brick.
DEFAULT_FALL_SPEED = 3


class PowerUp(pygame.sprite.Sprite):
    """A PowerUp represents the capsule that falls from a brick and enhances
    the game in some way when it collides with the paddle.
    PowerUp은 벽돌에서 떨어져 내려오는 '아이템 캡슐'을 나타낸다.
    패들과 충돌하면 게임 상태를 강화하거나(좋은 아이템),
    혹은 약화시키는(나쁜 아이템) 효과를 발동한다.
    
    This is an abstract base class that holds functionality common to all
    concrete powerups. All important powerup initialisation should
    take place in _activate() and not in the __init__() method to ensure
    that actions happen at the right time.
    """

    def __init__(self, game, brick, png_prefix, speed=DEFAULT_FALL_SPEED):
        """
        Initialise a new PowerUp.
         파워업을 초기화한다.

        Args:
            game:
                The current game instance.
                현재 Game 객체 (전체 상태 접근용)
            brick:
                The brick that triggered the powerup to drop.
                파워업이 떨어진 벽돌 객체
            png_prefix:
                The png file prefix that will be used to load the image
                sequence for the powerup animation.
                파워업 애니메이션 이미지 파일 경로의 접두사
            speed:
                Optional speed at which the powerup drops. Default 3 pixels
                per frame.
                낙하 속도(픽셀/프레임 단위), 기본값은 DEFAULT_FALL_SPEED(3)
        """
        super().__init__()
        self.game = game            # 게임 전체 상태 참조 (패들, 점수판, 스프라이트 그룹 등)
        self._speed = speed         # 아래로 떨어지는 속도

        SCALE_RATIO = 1.2   # 0.85처럼 살짝 작게 보이게 하고 싶으면 바꿔도 됨
        target_w = max(1, int(brick.rect.width  * SCALE_RATIO))
        target_h = max(1, int(brick.rect.height * SCALE_RATIO))
        
        # 여기부터 수정 완 ----------------
        # ─────────────────────────────────────────────
        # 2) 프레임 로드 + 스케일(없으면 투명 더미 한 장으로 대체)
        # ─────────────────────────────────────────────
        frames = []
        for img, _ in load_png_sequence(png_prefix):
            # 알파 보존
            img = img.convert_alpha()
            # 크기 다르면 스무스 스케일
            if img.get_size() != (target_w, target_h):
                img = pygame.transform.smoothscale(img, (target_w, target_h))
            frames.append(img)

        if not frames:
            # 프레임이 없어도 게임이 죽지 않도록 안전 장치
            LOG.warning("No frames for prefix '%s'. Using transparent fallback.", png_prefix)
            fallback = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
            # 가이드용 테두리를 보고 싶으면 주석 해제
            # pygame.draw.rect(fallback, (255, 0, 0), fallback.get_rect(), 1)
            frames = [fallback]

            #애니메이션 사이클과 첫 프레임
        self._animation = itertools.cycle(frames)
        self.image = next(self._animation)
        self._animation_start = 0

        # ─────────────────────────────────────────────
        # 3) 시작 위치: 벽돌 "정중앙 아래"에서 떨어지게(자연스러움)
        #    (원래 방식 쓰고 싶으면 아래 2줄 대신 bottomleft 방식 사용)
        # ─────────────────────────────────────────────
        self.rect = pygame.Rect(0, 0, target_w, target_h)
        self.rect.midtop = brick.rect.midbottom
        # 여기까지 수정 완 ------------------
        
        # 수정
        # # 애니메이션 프레임 순환자(cycle)
        # # load_png_sequence(png_prefix)가 반환한 이미지 리스트를 무한 반복
        # self._animation = itertools.cycle(
        #     image for image, _ in load_png_sequence(png_prefix))
        # self._animation_start = 0

        # self.image = None

        # #시작 위치: 벽돌 바로 아래쪽, 벽돌 크기와 동일한 폭·높이
        # self.rect = pygame.Rect(brick.rect.bottomleft,
        #                         (brick.rect.width, brick.rect.height))
        # ㅡㅡㅡㅡㅡ
        
        # 파워업이 화면을 벗어났는지 판단하기 위한 경계 영역(Rect)
        screen = pygame.display.get_surface()
        self._area = screen.get_rect()
        # visible=False가 되면 렌더링 및 업데이트에서 제외됨
        self.visible = True

    def update(self):
        # Move down by the specified speed.
        self.rect = self.rect.move(0, self._speed)

        if self._area.contains(self.rect):
            if self._animation_start % 4 == 0:
                # Animate the powerup.
                self.image = next(self._animation)

            # Check whether the powerup has collided with the paddle.
            if self.rect.colliderect(self.game.paddle.rect):
                # We've collided, so check whether it is appropriate for us
                # # to activate.
                if self._can_activate():
                    # If there is already an active powerup in the game,
                    # deactivate that first.
                    if self.game.active_powerup:
                        self.game.active_powerup.deactivate()
                    # Carry out the powerup specific activation behaviour.
                    self._activate()
                    # Set ourselves as the active powerup in the game.
                    self.game.active_powerup = self
                # No need to display ourself anymore.
                self.game.sprites.remove(self)
                self.visible = False
            else:
                # Keep track of the number of update cycles for animation
                # purposes.
                self._animation_start += 1

        else:
            # We're no longer on the screen.
            self.game.sprites.remove(self)
            self.visible = False

    def _activate(self):
        """Abstract hook method which should be overriden by concrete
        powerup subclasses to perform the powerup specific action.
        """
        raise NotImplementedError('Subclasses must implement _activate()')

    def _can_activate(self):
        """Whether it is appropriate for the powerup to activate given
        current game state.

        Returns:
            True if appropriate to activate, false otherwise.
        """
        if self.game.paddle.exploding or not self.game.paddle.visible:
            # Don't activate when the paddle is exploding or hidden.
            return False
        return True

    def deactivate(self):
        """Deactivate the current powerup by returning the game state back
        to what it was prior to the powerup taking effect.
        """
        raise NotImplementedError('Subclasses must implement deactivate()')


class ExtraLifePowerUp(PowerUp):     # 생명 추가

    def __init__(self, game, brick):
        super().__init__(game, brick, 'powerup_life')

    def _activate(self):

        self.game.lives += 1

    def deactivate(self):

        pass


class SlowBallPowerUp(PowerUp):      # slowdown 맞음

    _SLOW_BALL_SPEED = 6  # Pixels per frame.

    def __init__(self, game, brick):
        super().__init__(game, brick, 'powerup_slow')

        self._orig_speed = None

    def _activate(self):

        self._orig_speed = self.game.ball.base_speed

        for ball in self.game.balls:
            ball.speed = self._SLOW_BALL_SPEED
            ball.base_speed = self._SLOW_BALL_SPEED

    def deactivate(self):

        for ball in self.game.balls:
            ball.speed = self._orig_speed
            ball.base_speed = self._orig_speed


class ExpandPowerUp(PowerUp):        # 확장 맞음     

    def __init__(self, game, brick):
        super().__init__(game, brick, 'powerup_expand')

    def _activate(self):

        self.game.paddle.transition(WideState(self.game.paddle))
        for ball in self.game.balls:
            ball.base_speed += 1

    def deactivate(self):

        self.game.paddle.transition(NormalState(self.game.paddle))
        for ball in self.game.balls:
            ball.base_speed -= 1

    def _can_activate(self):
        can_activate = super()._can_activate()
        if can_activate:

            can_activate = not isinstance(self.game.active_powerup,
                                          self.__class__)
        return can_activate


class SpeedPowerUp(PowerUp):         # 스피드업

    _FAST_BALL_SPEED = 11  # Pixels per frame. (기존 6~10 정도에서 +)

    def __init__(self, game, brick):

        super().__init__(game, brick, 'powerup_speedup')
        self._orig_speed = None

    def _activate(self):

        self._orig_speed = self.game.ball.base_speed

        for ball in self.game.balls:
            ball.speed = self._FAST_BALL_SPEED
            ball.base_speed = self._FAST_BALL_SPEED

    def deactivate(self):
        if self._orig_speed is None:
            return  
        for ball in self.game.balls:
            ball.speed = self._orig_speed
            ball.base_speed = self._orig_speed


class CatchPowerUp(PowerUp):         # 얜 그냥 안씀            
    """This PowerUp allows the paddle to catch a ball.

    A ball is released by pressing the spacebar.
    """

    def __init__(self, game, brick):
        super().__init__(game, brick, 'powerup_catch')

    def _activate(self):
        """Add the ability to catch a ball when it collides with the
        paddle.
        """
        self.game.paddle.ball_collide_callbacks.append(self._catch)

        # Monitor for spacebar presses to release a caught ball.
        receiver.register_handler(pygame.KEYUP, self._release_ball)

    def deactivate(self):
        """Deactivate the CatchPowerUp from preventing the paddle from
        catching the ball.
        """
        self.game.paddle.ball_collide_callbacks.remove(self._catch)
        receiver.unregister_handler(self._release_ball)
        for ball in self.game.balls:
            ball.release()  # Release a currently caught ball.

    def _release_ball(self, event):
        """Release a caught ball when the spacebar is pressed."""
        if event.key == pygame.K_SPACE:
            for ball in self.game.balls:
                ball.release()

    def _catch(self, ball):
        """Catch the a when it collides with the paddle.
        Args:
            ball:
                The ball to be caught.
        """
        # Work out the position of the ball relative to the paddle.
        pos = (ball.rect.bottomleft[0] - self.game.paddle.rect.topleft[0],
               -ball.rect.height)
        ball.anchor(self.game.paddle, pos)


class DuplicatePowerUp(PowerUp):      # 복제 맞음
    
    def __init__(self, game, brick):
        super().__init__(game, brick, 'powerup_duplicate')

    def _activate(self):

        split_angle = 0.4 #복제가 일어나는곳

        for ball in list(self.game.balls):

            start_pos = ball.rect.center

            start_angle = ball.angle + split_angle #첫 번째 복제공 생성
            if start_angle > 2 * math.pi:
                start_angle -= 2 * math.pi

            ball1 = ball.clone(start_pos=start_pos,
                               start_angle=start_angle)

            start_angle = abs(ball.angle - split_angle) #2번

            ball2 = ball.clone(start_pos=start_pos,
                               start_angle=start_angle)

            self.game.balls.append(ball1) #게임에 공추가
            self.game.balls.append(ball2)

            self.game.sprites.append(ball1)
            self.game.sprites.append(ball2)

    def deactivate(self):
        pass




class ReducePowerUp(PowerUp):         # reduce
    def __init__(self, game, brick):
        super().__init__(game, brick, 'powerup_reduce')  # powerup_reduce_1.png 등과 연결

    def _activate(self):
        self.game.paddle.transition(NarrowState(self.game.paddle))
        # ⚠ 공 속도는 그대로 두기 (요청 반영)

    def deactivate(self):
        self.game.paddle.transition(NormalState(self.game.paddle))
        # ⚠ 공 속도 변화 없음

    def _can_activate(self):
        can_activate = super()._can_activate()
        if can_activate:
            # 이미 줄어든 상태면 또 줄이지 않기
            can_activate = not isinstance(self.game.active_powerup,
                                          self.__class__)
        return can_activate