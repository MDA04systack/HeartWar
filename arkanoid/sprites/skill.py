import pygame
import random
import logging
from arkanoid.sprites.ball import Ball
from arkanoid.sprites.paddle import Paddle
from arkanoid.sprites.brick import Brick
from arkanoid.sprites.enemy import Enemy, EnemyType

LOG = logging.getLogger(__name__)

class Game:
    def __init__(self):
        # 기존 초기화 코드
        self.screen = pygame.display.get_surface()
        self.clock = pygame.time.Clock()
        self.running = True

        self.all_sprites = pygame.sprite.Group()
        self.bricks = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()

        self.paddle = Paddle()
        self.all_sprites.add(self.paddle)

        self.ball = Ball(self.paddle, self.on_brick_collide)
        self.all_sprites.add(self.ball)

        # ------------------------------
        # 🔸 필살기 관련 변수 추가
        # ------------------------------
        self.special_ready = False      # 필살기 아이템을 먹은 상태
        self.special_used = False       # 이미 필살기를 썼는가
        self.special_item = None        # 화면에 존재하는 필살기 아이템
        self.special_item_image = pygame.image.load(
            "assets/special_item.png").convert_alpha()
        self.flash_timer = 0            # 화면 플래시 효과용
        # ------------------------------

        self._setup_enemies()

    # ============================================
    # 🔸 블록이 부서질 때 호출되는 함수 (예시용)
    # ============================================
    def on_brick_destroyed(self, brick):
        """블록이 깨질 때 호출됨"""
        if not self.special_item and not self.special_used:
            # 20% 확률로 필살기 아이템 등장
            if random.random() < 0.2:
                self.spawn_special_item(brick.rect.center)

        # 원래 있던 블록 제거 로직
        self.bricks.remove(brick)
        self.all_sprites.remove(brick)

    # ============================================
    # 🔸 필살기 아이템 생성 함수
    # ============================================
    def spawn_special_item(self, position):
        item = pygame.sprite.Sprite()
        item.image = self.special_item_image
        item.rect = item.image.get_rect(center=position)
        item.speed = 2
        item.visible = True
        self.special_item = item
        self.all_sprites.add(item)
        LOG.info("필살기 아이템 등장!")

    # ============================================
    # 🔸 필살기 발동 함수
    # ============================================
    def activate_special(self):
        LOG.info("필살기 발동!")
        # 화면 플래시 효과
        self.flash_timer = 10
        # 모든 적 폭발
        for enemy in list(self.enemies):
            if enemy.visible:
                enemy.explode()
        self.special_used = True
        self.special_ready = False

    # ============================================
    # 🔸 입력 처리
    # ============================================
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False

            # 🔸 S 키로 필살기 발동
            elif event.key == pygame.K_s:
                if self.special_ready and not self.special_used:
                    self.activate_special()

        self.paddle.handle_event(event)

    # ============================================
    # 🔸 적이 공 또는 패들과 충돌 시
    # ============================================
    def on_enemy_collide(self, enemy, collider):
        enemy.explode()

    # ============================================
    # 🔸 게임 오브젝트 업데이트
    # ============================================
    def update(self):
        self.all_sprites.update()

        # 🔸 필살기 아이템 낙하 및 획득 처리
        if self.special_item and self.special_item.visible:
            self.special_item.rect.y += self.special_item.speed
            # 바닥 도달 시 사라짐
            if self.special_item.rect.top > self.screen.get_height():
                self.all_sprites.remove(self.special_item)
                self.special_item = None
            # 패들과 충돌 시 필살기 획득
            elif self.special_item.rect.colliderect(self.paddle.rect):
                self.special_ready = True
                self.all_sprites.remove(self.special_item)
                self.special_item = None
                LOG.info("필살기 획득!")

    # ============================================
    # 🔸 화면 그리기
    # ============================================
    def draw(self):
        self.screen.fill((0, 0, 0))
        self.all_sprites.draw(self.screen)

        # 🔸 필살기 플래시 효과
        if self.flash_timer > 0:
            overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, 128))
            self.screen.blit(overlay, (0, 0))
            self.flash_timer -= 1

        pygame.display.flip()

    # ============================================
    # 🔸 게임 루프
    # ============================================
    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            self.update()
            self.draw()
            self.clock.tick(60)
