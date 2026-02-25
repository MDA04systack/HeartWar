import itertools
import logging
import math

import pygame

from arkanoid.event import receiver
from arkanoid.utils.util import (load_png,
                                 load_png_sequence)

LOG = logging.getLogger(__name__)


class Paddle(pygame.sprite.Sprite):
    """The movable paddle (a.k.a the "Vaus") used to control the ball to
    prevent it from dropping off the bottom of the screen."""

    def __init__(self, left_offset=0, right_offset=0, bottom_offset=0,
                 speed=10):
        """
        Create a new Paddle instance.

        The paddle will travel the entire width of the screen, unless the
        left and right offsets are specified which can restrict its travel.
        A bottom offset can also be supplied which defines how far from the
        bottom of the screen the paddle floats.

        Args:
            left_offset:
                Optional offset in pixels from the left of the screen that
                will restrict the maximum travel of the paddle.
            right_offset:
                Optional offset in pixels from the right of the screen that
                will restrict the maximum travel of the paddle.
            bottom_offset:
                The distance the paddle sits above the bottom of the screen.
            speed:
                Optional speed of the paddle in pixels per frame.
        """
        super().__init__()

        # The speed of the paddle movement in pixels per frame.
        self.speed = speed

        # The current movement in pixels. A negative value will trigger the
        # paddle to move left, a positive value to move right.
        self._move = 0

        # This toggles visibility of the paddle.
        self.visible = True

        # Load the default paddle image.
        self.image, self.rect = load_png('paddle')

        # Create the area the paddle can move laterally in.
        screen = pygame.display.get_surface().get_rect()
        self.area = pygame.Rect(screen.left + left_offset,
                                screen.height - bottom_offset,
                                screen.width - left_offset - right_offset,
                                self.rect.height)
        # Position the paddle.
        self.rect.center = self.area.center

        # A list of no-args callables that will be called on ball collision.
        self.ball_collide_callbacks = []

        # The current paddle state.
        self._state = NormalState(self)

    def update(self):


        self._state.update() #상태 업데이트 및 이동 명령

        if self._move:

            newpos = self.rect.move(self._move, 0) #새 위치 계산 및 경계 확인

            if self._area_contains(newpos):#경계 내 정상 이동 처리

                self.rect = newpos
            else: #경계 도달 시 정지 및 위치 보정

                while self._move != 0:
                    if self._move < 0:
                        self._move += 1
                    else:
                        self._move -= 1

                    newpos = self.rect.move(self._move, 0)
                    if self._area_contains(newpos):
                        self.rect = newpos
                        break

    def _area_contains(self, newpos):
        return self.area.collidepoint(newpos.midleft) and \
               self.area.collidepoint(newpos.midright)

    def transition(self, state):
        """Transition to the specified state.

        Note that this is a request to transition, notifying an existing state
        to exit, before switching to the new state. There therefore may be a
        delay before the supplied state becomes active.

        Args:
            state:
                The state to transition to.
        """
        def on_exit():
            # Switch the state on state exit.
            self._state = state
            state.enter()
            LOG.debug('Entered {}'.format(type(state).__name__))

        self._state.exit(on_exit)

    def move_left(self):
        """Tell the paddle to move to the left by the speed set when the
        paddle was initialised."""
        # Set the offset to negative to move left.
        self._move = -self.speed

    def move_right(self):
        """Tell the paddle to move to the right by the speed set when the
        paddle was initialised."""
        # A positive offset to move right.
        self._move = self.speed

    def stop(self):
        """Tell the paddle to stop moving."""
        self._move = 0

    def reset(self):
        """Reset the position of the paddle to its start position."""
        self.rect.center = self.area.center

    def deactivate_special_image(self):
        """
        Returns the paddle to its default size and appearance (NormalState).
        Called when the ball goes off-screen (lives lost).
        """
        if not isinstance(self._state, ExplodingState) and \
           not isinstance(self._state, NormalState):
            self.transition(NormalState(self))

    # ⭐ 1. 필살기 활성화 로직 수정 (다음 상태 전달하지 않음)
    def activate_special_image(self):
        """
        Called when a power-up is picked up.
        Triggers and maintains the custom transition animation indefinitely.
        """
        # 현재 상태가 이미 PowerUpTransitionState라면 무시
        if isinstance(self._state, PowerUpTransitionState):
            return

        # PowerUpTransitionState로 전환합니다. (WideState 전달 제거)
        self.transition(PowerUpTransitionState(self))

    # ⭐ 2. 필살기 사용 로직 추가
    def use_special_image(self):
        """
        Called when the player uses the special power-up (e.g., presses the spacebar).
        If the paddle is in the PowerUpTransitionState, it reverts to the NormalState.
        """
        if isinstance(self._state, PowerUpTransitionState):
            # NormalState로 전환하여 필살기 애니메이션을 해제합니다.
            self.transition(NormalState(self))
            LOG.debug("Special image power-up used and deactivated.")

    def on_ball_collide(self, paddle, ball):
        """Called when the ball collides with the paddle.

        This implementation delegates to the instance level
        ball_collide_callbacks list. To monitor for ball collisions, add
        a callback to that list. A callback will be passed the ball instance
        that collided.

        Args:
            paddle:
                The paddle that was struck.
            ball:
                The ball that struck the paddle.
        """
        for callback in self.ball_collide_callbacks:
            callback(ball)

    @property
    def exploding(self):
        return isinstance(self._state, ExplodingState)

    @staticmethod
    def bounce_strategy(paddle_rect, ball_rect):
        """Implementation of a ball bounce strategy used to calculate
        the angle that the ball bounces off the paddle. The angle
        of bounce is dependent upon where the ball strikes the paddle.

        Note: this function is not tied to the Paddle class but we house it
        here as it seems a reasonable place to keep it.

        Args:
            paddle_rect:
                The Rect of the paddle.
            ball_rect:
                The Rect of the ball.

        Returns:
            The angle of bounce in radians.
        """
        # Logically break the paddle into 6 segments.
        # Each segment triggers a different angle of bounce.
        segment_size = paddle_rect.width // 6
        segments = []

        for i in range(6):
            # Create rectangles for all segments bar the last.
            left = paddle_rect.left + segment_size * i
            if i < 5:
                # These segments are a fixed size.
                segment = pygame.Rect(left, paddle_rect.top, segment_size,
                                      paddle_rect.height)
            else:
                # The last segment makes up what is left of the paddle width.
                segment = pygame.Rect(left, paddle_rect.top,
                                      paddle_rect.width - (segment_size * 5),
                                      paddle_rect.height)
            segments.append(segment)

        # The bounce angles corresponding to each of the 8 segments.
        angles = 220, 245, 260, 280, 295, 320

        # Discover which segment the ball collided with. Just use the first.
        index = ball_rect.collidelist(segments)

        # Look up the angle and convert it to radians, before returning.
        return math.radians(angles[index])


class PaddleState:
    # ... (PaddleState 클래스 내용은 변경 없음) ...
    def __init__(self, paddle):
        self.paddle = paddle
        LOG.debug('Initialised {}'.format(type(self).__name__))

    def enter(self):
        pass

    def update(self):
        raise NotImplementedError('Subclasses must implement update()')

    def exit(self, on_exit):
        on_exit()

    def __repr__(self):
        class_name = type(self).__name__
        return '{}({!r})'.format(class_name, self.paddle)


class NormalState(PaddleState):
    # ... (NormalState 클래스 내용은 변경 없음) ...
    def __init__(self, paddle):
        super().__init__(paddle)

        self._pulsator = _PaddlePulsator(paddle, 'paddle_pulsate')

    def enter(self):
        """Set the default paddle graphic."""
        pos = self.paddle.rect.center
        self.paddle.image, self.paddle.rect = load_png('paddle')
        self.paddle.rect.center = pos

    def update(self):
        """Pulsate the paddle lights."""
        self._pulsator.update()


class _PaddlePulsator:
    # ... (_PaddlePulsator 클래스 내용은 변경 없음) ...
    def __init__(self, paddle, image_sequence_name):
        self._paddle = paddle
        self._image_sequence = load_png_sequence(image_sequence_name)
        self._animation = None
        self._update_count = 0

    def update(self):
        if self._update_count % 80 == 0:
            self._animation = itertools.chain(self._image_sequence,
                                              reversed(self._image_sequence))
            self._update_count = 0
        elif self._animation:
            try:
                if self._update_count % 4 == 0:
                    self._paddle.image, _ = next(self._animation)
            except StopIteration:
                self._animation = None

        self._update_count += 1


class MaterializeState(PaddleState):
    # ... (MaterializeState 클래스 내용은 변경 없음) ...
    def __init__(self, paddle):
        super().__init__(paddle)

        self._animation = iter(load_png_sequence('paddle_materialize'))
        self._update_count = 0

    def update(self):
        if self._update_count % 2 == 0:
            try:
                pos = self.paddle.rect.center
                self.paddle.image, self.paddle.rect = next(self._animation)
                self.paddle.rect.center = pos
            except StopIteration:
                self.paddle.transition(NormalState(self.paddle))

        self._update_count += 1


# ⭐ 3. PowerUpTransitionState의 생성자를 수정 (next_state 인자 제거)
class PowerUpTransitionState(PaddleState):
    """
    Animates the paddle using the 4 custom images indefinitely until deactivated.
    """

    def __init__(self, paddle): # 💡 next_state 인자를 제거했습니다.
        super().__init__(paddle)
        
        # 이미지를 무한으로 반복할 수 있도록 itertools.cycle을 사용합니다.
        image_sequence = load_png_sequence('powerup_active')
        self._animation = itertools.cycle(image_sequence) 
        self._update_count = 0

    def update(self):
        """Run the transition animation indefinitely."""
        # 애니메이션 속도 조절 (예: 매 3 프레임마다 업데이트)
        if self._update_count % 3 == 0:
            # cycle 덕분에 StopIteration 없이 무한 반복됩니다.
            pos = self.paddle.rect.center
            self.paddle.image, self.paddle.rect = next(self._animation)
            self.paddle.rect.center = pos

        self._update_count += 1


class WideState(PaddleState):
    # ... (WideState 클래스 내용은 원래대로 유지) ...
    def __init__(self, paddle):
        super().__init__(paddle)

        self._image_sequence = load_png_sequence('paddle_wide')
        self._animation = iter(self._image_sequence)

        self._pulsator = _PaddlePulsator(paddle, 'paddle_wide_pulsate')

        self._expand, self._shrink = True, False

        self._on_exit = None

    def update(self):
        if not self._expand and not self._shrink:
            self._pulsator.update()

        if self._expand:
            self._expand_paddle()
        elif self._shrink:
            self._shrink_paddle()

    def _expand_paddle(self):
        try:
            self._convert()
            while (not self.paddle.area.collidepoint(
                    self.paddle.rect.midleft)):
                self.paddle.rect = self.paddle.rect.move(1, 0)
            while (not self.paddle.area.collidepoint(
                    self.paddle.rect.midright)):
                self.paddle.rect = self.paddle.rect.move(-1, 0)
        except StopIteration:
            self._expand = False

    def _shrink_paddle(self):
        try:
            self._convert()
        except StopIteration:
            self._shrink = False
            self._on_exit()

    def _convert(self):
        pos = self.paddle.rect.center
        self.paddle.image, self.paddle.rect = next(self._animation)
        self.paddle.rect.center = pos

    def exit(self, on_exit):
        self._shrink = True
        self._on_exit = on_exit
        self._animation = iter(reversed(self._image_sequence))


class NarrowState(PaddleState):
    # ... (NarrowState 클래스 내용은 변경 없음) ...
    def __init__(self, paddle):
        super().__init__(paddle)

        self._image_sequence = load_png_sequence('paddle_narrow')
        if not self._image_sequence:
            raise ValueError("paddle_narrow images not found")
        
        self._animation = iter(self._image_sequence)
        self._shrink = True
        self._expand = False
        self._on_exit = None

    def update(self):
        if self._shrink:
            self._shrink_paddle()
        elif self._expand:
            self._expand_paddle()

    def _shrink_paddle(self):
        try:
            self._convert()
        except StopIteration:
            self._shrink = False

    def _expand_paddle(self):
        try:
            self._convert()
        except StopIteration:
            self._expand = False
            if self._on_exit:
                self._on_exit()


    def _convert(self):
        pos = self.paddle.rect.center
        self.paddle.image, self.paddle.rect = next(self._animation)
        self.paddle.rect.center = pos

    def exit(self, on_exit):
        self._expand = True
        self._on_exit = on_exit
        self._animation = iter(reversed(self._image_sequence))


class LaserState(PaddleState):
    # ... (LaserState 클래스 내용은 변경 없음) ...
    def __init__(self, paddle, game):
        super().__init__(paddle)
        self._game = game

        self._image_sequence = load_png_sequence('paddle_laser')
        self._laser_anim = iter(self._image_sequence)

        self._to_laser, self._from_laser = True, False

        self._pulsator = _PaddlePulsator(paddle, 'paddle_laser_pulsate')

        self._bullets = []

        self._on_exit = None

    def update(self):
        if not self._to_laser and not self._from_laser:
            self._pulsator.update()

        if self._to_laser:
            self._convert_to_laser()
        elif self._from_laser:
            self._convert_from_laser()

    def _convert_to_laser(self):
        try:
            self._convert()
        except StopIteration:
            self._to_laser = False
            receiver.register_handler(pygame.KEYUP, self._fire)

    def _convert_from_laser(self):
        try:
            self._convert()
        except StopIteration:
            self._from_laser = False
            self._on_exit()

    def _convert(self):
        pos = self.paddle.rect.center
        self.paddle.image, self.paddle.rect = next(self._laser_anim)
        self.paddle.rect.center = pos
        while (not self.paddle.area.collidepoint(
                self.paddle.rect.midleft)):
            self.paddle.rect = self.paddle.rect.move(1, 0)
        while (not self.paddle.area.collidepoint(
                self.paddle.rect.midright)):
            self.paddle.rect = self.paddle.rect.move(-1, 0)

    def exit(self, on_exit):
        self._to_laser = False
        self._from_laser = True
        self._on_exit = on_exit
        self._laser_anim = iter(reversed(self._image_sequence))
        receiver.unregister_handler(self._fire)

    def _fire(self, event):
        if event.key == pygame.K_SPACE:
            self._bullets = [bullet for bullet in self._bullets if
                             bullet.visible]
            if len(self._bullets) < 3:
                left, top = self.paddle.rect.bottomleft
                bullet1 = LaserBullet(self._game, position=(left + 10, top))
                bullet2 = LaserBullet(self._game, position=(
                    left + self.paddle.rect.width - 10, top))

                self._bullets.append(bullet1)
                self._bullets.append(bullet2)

                self._game.sprites.append(bullet1)
                self._game.sprites.append(bullet2)

                bullet1.release()
                bullet2.release()


class LaserBullet(pygame.sprite.Sprite):
    # ... (LaserBullet 클래스 내용은 변경 없음) ...
    def __init__(self, game, position, speed=15):
        super().__init__()
        self.image, self.rect = load_png('laser_bullet')

        self._game = game
        self._position = position
        self._speed = speed

        screen = pygame.display.get_surface()
        self._area = screen.get_rect()

        self.visible = False

    def release(self):
        self.rect.midbottom = self._position
        self.visible = True

    def update(self):
        if self.visible:
            self.rect = self.rect.move(0, -self._speed)
            top_edge_collision = pygame.sprite.spritecollide(
                self,
                [self._game.round.edges.top],
                False)

            if not top_edge_collision:
                visible_bricks = (brick for brick in self._game.round.bricks
                                  if brick.visible)
                brick_collide = pygame.sprite.spritecollide(self,
                                                            visible_bricks,
                                                            False)

                if brick_collide:
                    brick = brick_collide[0]
                    brick.value = 0
                    brick.powerup_cls = None
                    self._game.on_brick_collide(brick, self)
                    self.visible = False
                else:
                    visible_enemies = (
                        enemy for enemy in self._game.enemies if enemy.visible)
                    enemy_collide = pygame.sprite.spritecollide(
                        self,
                        visible_enemies,
                        False)
                    if enemy_collide:
                        self._game.on_enemy_collide(enemy_collide[0], self)
                        self.visible = False
            else:
                self.visible = False


class ExplodingState(PaddleState):
    # ... (ExplodingState 클래스 내용은 변경 없음) ...
    def __init__(self, paddle, on_exploded):
        super().__init__(paddle)

        self._exploding_animation = iter(load_png_sequence('paddle_explode'))
        self._on_explode_complete = on_exploded
        self._rect_orig = None

        self._update_count = 0

    def enter(self):
        self._rect_orig = self.paddle.rect

    def update(self):
        if 10 < self._update_count:
            if self._update_count % 4 == 0:
                try:
                    self.paddle.image, self.paddle.rect = next(
                        self._exploding_animation)
                    self.paddle.rect.center = self._rect_orig.center
                except StopIteration:
                    self._on_explode_complete()
                    self.paddle.visible = False

        self.paddle.stop()
        self._update_count += 1