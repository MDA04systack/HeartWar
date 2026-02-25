import enum
import itertools
import logging
import math
import random
import weakref

import pygame

from arkanoid.utils.util import load_png_sequence

LOG = logging.getLogger(__name__)

SPEED = 2 # 적 이동 속도
START_DIRECTION = 1.57  #초기 이동 방향: 아래쪽(Radians)
START_DURATION = 75  # 초기 방향으로 이동할 프레임 수


# A value between these two bounds will be randomly selected for the
# duration of travel (i.e. number of frames) in a given direction.
MIN_DURATION = 30
MAX_DURATION = 60

# A value between this and its negative will be chosen at random and then
# added to the direction of the sprite. This ensures some erraticness in the
# sprites' movement.
RANDOM_RANGE = 1.5  # 자유 이동 시 현재 방향에 더해져 움직임을 불규칙하게 만드는 무작위 범위(Radians)

TWO_PI = math.pi * 2
HALF_PI = math.pi / 2


class EnemyType(enum.Enum):

    """Enumeration of enemy types to their image sequence prefix.
    """

    cube = 'enemy_cube'
    cone = 'enemy_cone'
    molecule = 'enemy_molecule'
    pyramid = 'enemy_pyramid'
    sphere = 'enemy_sphere'


class Enemy(pygame.sprite.Sprite):

    _enemies = weakref.WeakSet()

    def __init__(self, enemy_type, paddle, on_paddle_collide,
                 collidable_sprites, on_destroyed):
       
        super().__init__()
        self._enemies.add(self)
        self._paddle = paddle
        self._on_paddle_collide = on_paddle_collide
        self._on_destroyed = on_destroyed # 적이 파괴되었을 때 호출되는 콜백 함수
        self._on_destroyed_called = False

        screen = pygame.display.get_surface() #화면 영역 이미지 로드
        self._area = screen.get_rect()

        self._animation, width, height = self._load_animation_sequence(
            enemy_type.value)

        self.rect = pygame.Rect(self._area.center, (width, height))
        self.image = None

    
        self._explode_animation = None #폭발 상태

        # The sprites in the game that cause the enemy sprite to change
        # direction when it collides with them.
        self._collidable_sprites = pygame.sprite.Group()
        for sprite in collidable_sprites:
            self._collidable_sprites.add(sprite)

        # The current direction of travel of the sprite.
        self._direction = START_DIRECTION

        # The duration which the sprite will travel in a set direction.
        # This is an update count value. When the update count reaches this
        # value, the direction will be recalculated.
        self._duration = START_DURATION

        # The enemy sprite is in contact mode after it collides with another
        # sprite that causes it to change direction (rather than destroy it).
        # It remains in contact mode for a number of cycles after the last
        # collision. This attribute tracks the last cycle a contact was made.
        self._last_contact = 0

        # Stops the enemy sprite from moving if set to True.
        self.freeze = False

        # Track the number of update cycles.
        self._update_count = 0

        # Sprite visibility toggle.
        self.visible = True

    def _load_animation_sequence(self, filename_prefix):
        """Load and return the image sequence for the animated sprite, and
        with it, the maximum width and height of the images in the sequence.

        Args:
            filename_prefix:
                The prefix of the image sequence.
        Returns:
            A 3-element tuple: the itertools.cycle object representing the
            animated sequence, the maximum width, the maximum height.
        """
        sequence = load_png_sequence(filename_prefix)
        max_width, max_height = 0, 0

        for image, rect in sequence:
            if rect.width > max_width:
                max_width = rect.width
            if rect.height > max_height:
                max_height = rect.height

        return itertools.cycle(sequence), max_width, max_height

    def update(self):
        """Update the enemy's position, handling any collisions."""
        if self._explode_animation: #폭발 애니메이션이 진행 중이면 _explode()를 호출하고 종료
            self._explode()
        else:
            if self._update_count % 4 == 0:
                # 4프레임마다 적의 이미지를 업데이트하여 애니메이션 효과를 냄
                self.image, _ = next(self._animation)

            if not self.freeze:
                # 현재 _direction과 SPEED를 사용하여 적의 새로운 위치를 계산
                self.rect = self._calc_new_position()
                # 적이 화면 영역 안에 있을 때 실행되는 블록
                if self._area.contains(self.rect):
                    # 패들과 충돌했는지 확인하고, 충돌 시 _on_paddle_collide 콜백 호출
                    if pygame.sprite.spritecollide(self, [self._paddle],
                                                   False):
                        self._on_paddle_collide(self, self._paddle)
                    else:
                        visible_sprites = itertools.chain(
                            (sprite for sprite in self._collidable_sprites if
                             sprite.visible),
                            (sprite for sprite in self._enemies if
                             sprite.visible and sprite is not self)
                        )
                        sprites_collided = pygame.sprite.spritecollide(
                            self,
                            visible_sprites, None) # 다른 적이나 충돌 가능한 스프라이트 (벽, 벽돌 등)와 충돌했는지 확인

                        # The following code could be pulled into a separate
                        # strategy class which could be passed to the enemy
                        # when it is initialised. This could act as the default
                        # movement behaviour, and would allow rounds to
                        # inject their own strategy classes when they wanted
                        # their own round specific movement behaviour.
                        #####################################################

                        if sprites_collided: # 충돌체가 있으면 _calc_direction_collision()을 호출하여 방향을 바꿈
                            self._last_contact = self._update_count
                            self._direction = self._calc_direction_collision(
                                sprites_collided)
                        elif self._update_count > self._last_contact + 30:
                            # Last contact not made for past 30 updates, so
                            # recalculate direction using free movement
                            # algorithm.
                            
                            # 충돌이 없었던 경우, _duration이 만료되면 _calc_direction()을 호출하여 자유 이동 방향 (패들 쪽 + 무작위성)을 재계산
                            if not self._duration:
                                # The duration of the previous direction of
                                # free movement has elapsed, so calculate a new
                                # direction with a new duration.
                                self._direction = self._calc_direction()
                                self._duration = (
                                    self._update_count + random.choice(
                                        range(MIN_DURATION, MAX_DURATION)))
                            elif self._update_count >= self._duration:
                                # We've reached the maximum duration in the
                                # given direction, so reset in order for the
                                # direction to be modified next cycle.
                                self._duration = 0

                        #####################################################
                else:
                    # We've dropped off the bottom of the screen.
                    #if not self._on_destroyed_called: # 기존코드 삭제
                        #self._on_destroyed(self)
                        #self._on_destroyed_called = True
                    # [수정21] 25.11.14 적 행동 로직 변경 코드 추가
                    # 적이 화면 하단 경계를 벗어난 경우 (벽에 부딪힌 것처럼 튕겨 나오게 함)
                    # self.rect.bottom이 화면 하단 경계(self._area.bottom)를 넘어선 경우를 처리
                    
                    # 하단 이탈 감지
                    if self.rect.bottom > self._area.bottom:
                        # 1. 위치를 화면 경계 안으로 되돌림
                        self.rect.bottom = self._area.bottom
                        # 2. 방향을 반전시킴. (천장에 부딪힌 것처럼)
                        # 새로운 방향은 현재 방향(self._direction)을 수평선(0, pi)에 대해 대칭 이동시킴
                        # 즉, self._direction = TWO_PI - self._direction
                        self._direction = TWO_PI - self._direction
                        # 3. 속도가 '0'이나 'pi' 근처인 경우, 튕겨나오지 않고 수평 이동만 할 수 있으므로
                        # 약간의 무작위성을 추가하여 하단에 붙어있지 않게함
                        if abs(self._direction) < 0.1 or abs(self._direction - math.pi) < 0.1:
                            # 방향을 위쪽으로 살짝 틀어줌
                            self._direction += random.uniform(HALF_PI/2, HALF_PI)
                    # 좌우 이탈 처리 (선택적으로 경계 안으로 되돌림)
                    elif self.rect.right > self._area.right or self.rect.left < self._area.left:
                        # 좌우 이탈 시에는 기존 벽 충돌 로직이 작동하도록 경계 안으로 되돌림
                        # (Enemy 클래스는 좌우 벽에 닿으면 방향을 바꾸도록 설계되어 있으므로
                        #  이탈 시 강제로 경계 안으로 위치만 수정)
                        if self.rect.right > self._area.right:
                            self.rect.right = self._area.right
                        elif self.rect.left < self._area.left:
                            self.rect.left = self._area.left

        self._update_count += 1

    # 적이 공이나 패들에 맞아 파괴될 때 폭발 애니메이션을 처리
    def _explode(self):
        try: # 폭발 애니메이션 시퀀스(_explode_animation)의 프레임을 모두 사용하면 발생하는 StopIteration 예외를 잡음
            if self._update_count % 2 == 0:
                rect = self.rect
                self.image, self.rect = next(self._explode_animation)
                self.rect.center = rect.center
        except StopIteration:
            self._explode_animation = None
            # [수정22] 콜백이 None이 아닐 때만 호출하도록 변경
            if self._on_destroyed:
                self._on_destroyed(self) # 콜백을 호출하여 적을 게임에서 최종적으로 제거

    def _calc_new_position(self):
        offset_x = SPEED * math.cos(self._direction)
        offset_y = SPEED * math.sin(self._direction)

        return self.rect.move(offset_x, offset_y)

    def _calc_direction_collision(self, sprites_collided):
        """Calculate a new direction based upon the sprites we collided with.

        Args:
            sprites_collided:
                A list of sprites that we have collided with.
        Returns:
            The direction in radians.
        """
        # Map out the sides of the object, excluding the corners. Here we use
        # 5 pixel wide rectangles to represent each side.
        top = pygame.Rect(self.rect.left + 5, self.rect.top,
                          self.rect.width - 10, 5)
        left = pygame.Rect(self.rect.left, self.rect.top + 5, 5,
                           self.rect.height - 10)
        bottom = pygame.Rect(self.rect.left + 5, self.rect.top +
                             self.rect.height - 5, self.rect.width - 10, 5)
        right = pygame.Rect(self.rect.left + self.rect.width - 5,
                            self.rect.top + 5, 5, self.rect.height - 10)

        rects = [sprite.rect for sprite in sprites_collided]
        cleft, cright, ctop, cbottom = False, False, False, False

        for rect in rects:
            # Work out which of our sides are in contact.
            cleft = cleft or left.colliderect(rect)
            cright = cright or right.colliderect(rect)
            ctop = ctop or top.colliderect(rect)
            cbottom = cbottom or bottom.colliderect(rect)

        direction = self._direction

        # Work out the new direction based on what we've collided with.
        if cleft and cright and ctop and cbottom:
            # When all 4 sides collide, try to send back in direction
            # from which originated. Should probably freeze instead.
            direction = -direction
        elif cleft and cright and cbottom:
            direction = math.pi + HALF_PI
        elif cleft and cright and ctop:
            direction = HALF_PI
        elif cleft and cbottom:
            direction = 0
        elif cright and cbottom:
            direction = math.pi
        elif cbottom:
            if direction not in (0, math.pi):
                direction = 0
        else:
            # Any other combination causes a downward direction. This may
            # include a corner collision - as we don't detect those.
            direction = math.pi - HALF_PI
            if cleft or cright:
                # Prevent the sprite from getting 'stuck' to walls.
                if self._update_count % 60 == 0:
                    if cright:
                        direction = math.pi
                    else:
                        direction = 0

        return direction

    # 충돌이 없을 때, 적이 이동할 새로운 방향을 결정
    def _calc_direction(self):
        """Calculate the direction of travel when the sprite is moving
        freely (has not collided).

        When moving freely (not colliding) the enemy sprites will gradually
        move towards the paddle.

        Returns:
            The direction in radians.
        """
        # No collision, so calculate the direction towards the paddle
        # but with some randomness applied.
        paddle_x, paddle_y = self._paddle.rect.center
        direction = math.atan2(paddle_y - self.rect.y,
                               paddle_x - self.rect.x)
        # 적의 위치에서 패들 중앙을 향하는 정확한 방향을 계산
        
        # 계산된 방향에 RANDOM_RANGE 내의 무작위 값을 더하여 움직임에 불규칙성 추가
        direction += random.uniform(-RANDOM_RANGE, RANDOM_RANGE)

        return direction

    def explode(self):
        """Trigger an explosion of the enemy sprite."""
        if not self._explode_animation:
            self._explode_animation = iter(
                load_png_sequence('enemy_explosion'))

    def reset(self):
        """Reset the enemy state back to its starting state."""
        self._direction = START_DIRECTION
        self._duration = START_DURATION
        self._on_destroyed_called = False
        self.visible = True
        self.freeze = False
